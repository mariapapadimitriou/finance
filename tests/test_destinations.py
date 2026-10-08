"""Where a transfer went is learned once, by destination, and applied only to
what matching leaves unmatched."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest, recategorize_all
from finance.transfers import UNSORTED, destination

TODAY = date.today()


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, description, account="chq", when=None, who=None, kind="depository"):
    raw = {"account_type": kind}
    if who:
        raw["counterparty"] = who
    return Transaction(date=when or day(1), description=description, amount=amount,
                       account_id=account, account_name=account, raw=raw)


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "dest.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t for t in st.all_transactions()}


class TestTheKey:
    def test_plaid_counterparty_wins(self):
        assert destination(row(50, "SEND E-TFR ***Q7k", who="Ana Lopez")) == \
            ("to:ana lopez", "Ana Lopez")

    @pytest.mark.parametrize("text", ["TFR-TO 1234567", "TFR-TO 12-34567",
                                      "TRANSFER TO 004 1234567", "TFR-FR ••4567"])
    def test_account_digits(self, text):
        assert destination(row(50, text))[0] == "acct:4567"

    def test_a_specific_name_without_its_reference(self):
        assert destination(row(50, "QUESTRADE INC #88231"))[0] == "name:questrade inc"

    def test_a_bare_e_transfer_has_nothing_to_learn(self):
        assert destination(row(50, "SEND E-TFR")) is None


class TestRules:
    def sort(self, c, ids, category):
        return c.post("/api/transfers/sort", json={"ids": ids, "category": category,
                                                   "remember": True}).get_json()

    def test_learned_once_then_automatic(self, client):
        st = client.application.config["STORE"]
        load(st, row(100, "SEND E-TFR ***A1b", who="Ana Lopez", when=day(9)))
        g = client.get("/api/transfers/unsorted").get_json()["groups"][0]
        assert g["merchant"] == "Ana Lopez" and g["learnable"]
        assert self.sort(client, g["ids"], "Gifts & Charity")["learned"] == 1
        # A new transfer to her, with a new reference: sorted by itself.
        rows = load(st, row(60, "SEND E-TFR ***Zz9", who="Ana Lopez", when=day(2)))
        assert rows["SEND E-TFR ***Zz9"].category == "Gifts & Charity"
        assert client.get("/api/transfers/unsorted").get_json()["count"] == 0

    def test_a_rule_never_overrides_a_match(self, client):
        st = client.application.config["STORE"]
        load(st, row(500, "TFR-TO 1234567", when=day(9)))
        g = client.get("/api/transfers/unsorted").get_json()["groups"][0]
        self.sort(client, g["ids"], "Saved")
        # Later a $500 lands on a connected account the same day as a new one.
        rows = load(st, row(500, "TFR-TO 1234567", when=day(3)),
                    row(-500, "TFR-FR 7654321", account="sav", when=day(3)))
        assert rows["TFR-TO 1234567"] is not None
        cats = sorted(t.category for t in st.all_transactions() if t.amount == 500)
        assert cats == ["Saved", "Transfers"]

    def test_a_rule_survives_a_resort(self, client):
        st = client.application.config["STORE"]
        load(st, row(300, "TFR-TO 1234567", when=day(4)))
        g = client.get("/api/transfers/unsorted").get_json()["groups"][0]
        self.sort(client, g["ids"], "Saved")
        recategorize_all(st)
        assert st.all_transactions()[0].category == "Saved"

    def test_undo_clears_the_rule(self, client):
        st = client.application.config["STORE"]
        load(st, row(300, "TFR-TO 1234567", when=day(4)))
        g = client.get("/api/transfers/unsorted").get_json()["groups"][0]
        self.sort(client, g["ids"], "Saved")
        r = client.post(f"/api/transactions/{g['ids'][0]}/unsort").get_json()
        assert r["category"] == UNSORTED and st.destinations() == {}

    def test_without_remember_only_these_rows(self, client):
        st = client.application.config["STORE"]
        load(st, row(300, "TFR-TO 1234567", when=day(4)))
        g = client.get("/api/transfers/unsorted").get_json()["groups"][0]
        client.post("/api/transfers/sort", json={"ids": g["ids"], "category": "Saved"})
        assert st.destinations() == {}
        rows = load(st, row(80, "TFR-TO 1234567", when=day(1)))
        assert rows["TFR-TO 1234567"].category in ("Saved", UNSORTED)
        assert client.get("/api/transfers/unsorted").get_json()["count"] == 1


def test_old_transfer_overrides_become_destination_rules(client):
    st = client.application.config["STORE"]
    load(st, row(400, "SEND E-TFR TO ANA", when=day(5)))
    t = st.all_transactions()[0]
    st.set_override(t.merchant, "Saved")
    st.set_setting("categories_version", "0")
    with st.conn() as c:
        c.execute("DELETE FROM settings WHERE key = 'destinations_migrated'")
    recategorize_all(st)
    assert st.overrides() == {}
    assert "Saved" in st.destinations().values()
    assert st.all_transactions()[0].category == "Saved"
