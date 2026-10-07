"""Every dollar out is spent or saved; only a transfer Spendie can see both
ends of is neutral."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.analytics import counts_as_spending
from finance.categorize import CATEGORIES, is_discretionary
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest, recategorize_all
from finance.store import Store
from finance.transfers import UNSORTED, match_transfers

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


def day(n: int) -> str:
    """A date in this month, never in the future."""
    return (TODAY.replace(day=1) + timedelta(days=n)).isoformat() \
        if TODAY.day > n else TODAY.isoformat()


def row(amount, description, account="chq", kind="depository", when=None, **kw):
    return Transaction(date=when or TODAY.isoformat(), description=description,
                       amount=amount, account_id=account,
                       account_name={"chq": "Chequing", "card": "TD Visa"}.get(account, account),
                       raw={"account_type": kind} if kind else {}, **kw)


def load(st, *rows):
    by_account: dict[str, list] = {}
    for r in rows:
        by_account.setdefault(r.account_id, []).append(r)
    for acct, txns in by_account.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t for t in st.all_transactions()}


@pytest.fixture()
def st(tmp_path):
    return Store(str(tmp_path / "t.db"))


class TestTheCategories:
    def test_unsorted_is_spending_but_not_the_weekly_number(self):
        assert UNSORTED in CATEGORIES and not is_discretionary(UNSORTED)
        t = Transaction(date="2026-01-01", description="x", amount=10,
                        account_id="a", category=UNSORTED)
        assert counts_as_spending(t)

    def test_saved_replaces_investments_on_open(self, tmp_path):
        path = str(tmp_path / "old.db")
        st = Store(path)
        st.add_transactions([Transaction(date="2026-01-02", description="QUESTRADE",
                                         amount=500, account_id="a",
                                         category="Investments")])
        with st.conn() as c:
            c.execute("INSERT INTO merchant_overrides (merchant_key, category) "
                      "VALUES ('questrade', 'Investments')")
        st = Store(path)
        assert st.all_transactions()[0].category == "Saved"
        assert st.overrides()["questrade"] == "Saved"


class TestMatching:
    def test_a_card_payment_seen_on_both_ends_is_neutral(self, st):
        rows = load(st,
                    row(900, "TD VISA PREAUTH PYMT", when=day(1)),
                    row(-900, "PAYMENT - THANK YOU", account="card", kind="credit",
                        when=day(3)))
        assert rows["TD VISA PREAUTH PYMT"].category == "Transfers"
        assert not counts_as_spending(rows["TD VISA PREAUTH PYMT"])

    def test_money_leaving_for_somewhere_unseen_is_unsorted_and_spent(self, st):
        rows = load(st, row(500, "SEND E-TFR ***abc"))
        t = rows["SEND E-TFR ***abc"]
        assert t.category == UNSORTED and counts_as_spending(t)

    def test_the_other_end_arriving_later_clears_it(self, st):
        load(st, row(700, "TFR-TO 1234", when=day(0)))
        rows = load(st, row(-700, "TFR-FROM 9876", account="sav", when=day(1)))
        assert rows["TFR-TO 1234"].category == "Transfers"

    def test_one_arrival_pairs_with_one_departure(self, st):
        rows = load(st,
                    row(300, "SEND E-TFR one", when=day(0)),
                    row(300, "SEND E-TFR two", when=day(0)),
                    row(-300, "TFR-FROM sav", account="sav", when=day(1)))
        cats = sorted([rows["SEND E-TFR one"].category, rows["SEND E-TFR two"].category])
        assert cats == ["Transfers", UNSORTED]

    def test_too_far_apart_is_not_a_match(self):
        out = match_transfers([
            row(250, "SEND E-TFR", when="2026-03-01", category="Transfers"),
            row(-250, "TFR-FROM", account="sav", when="2026-03-08", category="Transfers"),
        ])
        assert list(out.values()) == [UNSORTED]

    def test_the_same_account_is_not_its_own_other_end(self):
        out = match_transfers([
            row(250, "SEND E-TFR", category="Transfers"),
            row(-250, "E-TFR IN", category="Transfers"),
        ])
        assert list(out.values()) == [UNSORTED]

    def test_a_cards_own_transfers_and_statements_are_left_alone(self, st):
        rows = load(st,
                    row(1000, "BALANCE TRANSFER", account="card", kind="credit"),
                    row(80, "SEND E-TFR csv", account="csvacct", kind=None))
        assert rows["BALANCE TRANSFER"].category == "Transfers"
        assert rows["SEND E-TFR csv"].category == "Transfers"

    def test_your_own_choices_are_never_touched(self, st):
        rows = load(st, row(500, "SEND E-TFR mine"), row(400, "QTRADE xfer"))
        st.set_transaction_category(rows["SEND E-TFR mine"].fingerprint, "Transfers")
        st.set_override("QTRADE xfer", "Transfers")
        recategorize_all(st)
        after = {t.description: t for t in st.all_transactions()}
        assert after["SEND E-TFR mine"].category == "Transfers"
        assert after["QTRADE xfer"].category == "Transfers"

    def test_a_resort_puts_them_back(self, st):
        load(st, row(500, "SEND E-TFR again"))
        recategorize_all(st)
        assert st.all_transactions()[0].category == UNSORTED


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "api.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


def month_spend(c):
    return next(m["spend"] for m in c.get("/api/summary").get_json()["monthly"]
                if m["month"] == MONTH)


class TestSortingThem:
    @pytest.fixture()
    def unsorted_row(self, client):
        st = client.application.config["STORE"]
        load(st, row(500, "SEND E-TFR ***xyz", when=day(1)),
             row(20, "COFFEE SHOP", account="card", kind="credit", when=day(1)))
        return st, next(t for t in st.all_transactions() if t.category == UNSORTED)

    def test_listed_with_a_count(self, client, unsorted_row):
        body = client.get("/api/transfers/unsorted").get_json()
        assert body["count"] == 1 and body["total"] == 500
        t = body["transfers"][0]
        assert t["merchant"] and t["account_name"] == "Chequing" and t["amount"] == 500

    def test_saved_stops_counting_and_shows_on_ahead(self, client, unsorted_row):
        _, t = unsorted_row
        before = month_spend(client)
        client.patch(f"/api/transactions/{t.fingerprint}", json={"category": "Saved"})
        assert month_spend(client) == pytest.approx(before - 500)
        assert client.get("/api/projections").get_json()["invested_month"]["amount"] == 500
        assert client.get("/api/transfers/unsorted").get_json()["count"] == 0

    def test_spent_takes_its_category(self, client, unsorted_row):
        _, t = unsorted_row
        before = month_spend(client)
        client.patch(f"/api/transactions/{t.fingerprint}", json={"category": "Gifts & Charity"})
        assert month_spend(client) == pytest.approx(before)
        rows = client.get("/api/transactions").get_json()["transactions"]
        assert next(r for r in rows if r["id"] == t.fingerprint)["category"] == "Gifts & Charity"

    def test_always_sorts_the_next_one_by_itself(self, client, unsorted_row):
        st, t = unsorted_row
        client.patch(f"/api/transactions/{t.fingerprint}",
                     json={"category": "Saved", "apply_to_merchant": True})
        rows = load(st, row(500, "SEND E-TFR ***xyz", when=day(2)))
        assert all(r.category == "Saved" for r in st.all_transactions()
                   if r.merchant == t.merchant)
        assert client.get("/api/transfers/unsorted").get_json()["count"] == 0
