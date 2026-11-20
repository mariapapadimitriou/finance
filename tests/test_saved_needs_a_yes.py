"""Saved needs her Yes (product owner, 2026-11-20): a transfer into a
savings or investment account, or to an investment firm, is a transfer until
she answers "Is X where you save?" once; her answer holds for the account or
destination from then on. Asked whatever happens to Your plan."""

from datetime import date

import pytest

from app import create_app
from finance import checks
from finance.ingest import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def row(amount, description, account="chq", kind="depository", issuer=None, **kw):
    raw = {"account_type": kind}
    if issuer:
        raw["issuer_category"] = issuer
    return Transaction(date=TODAY.isoformat(), description=description, amount=amount,
                       account_id=account, account_name=account, raw=raw, **kw)


@pytest.fixture()
def app(tmp_path):
    app = create_app(str(tmp_path / "yes.db"))
    app.config.update(TESTING=True)
    return app


def load(st, *rows):
    by = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for account, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=account))
    return {t.description: t for t in st.all_transactions()}


class TestALinkedInvestmentAccount:
    def test_asked_once_and_her_yes_makes_it_saved(self, app):
        st = app.config["STORE"]
        st.note_account("chq", name="TD Chequing ••1111", item_id="i", account_type="depository", subtype="checking")
        st.note_account("inv", name="Wealthsimple TFSA ••3333", item_id="i", enabled=False,
                        account_type="investment", subtype="tfsa")
        rows = load(st, row(500.0, "TFR-TO 12343333", category="Transfers"))
        assert rows["TFR-TO 12343333"].category == "Transfers"
        with app.test_client() as c:
            review = c.get("/api/review").get_json()
            asks = {q["key"]: q for q in review["checks"]}
            assert "chk:saver:inv" in asks, "asked even while Your plan is parked"
            assert asks["chk:saver:inv"]["pair"]["question"] == "Is Wealthsimple TFSA ••3333 where you save?"
            r = c.post("/api/review/check/chk:saver:inv", json={"yes": True})
            assert r.status_code == 200
            assert "chk:saver:inv" not in {q["key"] for q in c.get("/api/review").get_json()["checks"]}
        assert {t.description: t for t in st.all_transactions()}["TFR-TO 12343333"].category == "Saved"

    def test_her_no_keeps_it_a_transfer_and_asks_no_more(self, app):
        st = app.config["STORE"]
        st.note_account("inv", name="RBC Savings ••2222", item_id="i", account_type="depository", subtype="savings")
        load(st, row(-200.0, "TRANSFER IN", account="inv", issuer="TRANSFER_IN_SAVINGS"))
        with app.test_client() as c:
            assert "chk:saver:inv" in {q["key"] for q in c.get("/api/review").get_json()["checks"]}
            c.post("/api/review/check/chk:saver:inv", json={"yes": False})
            assert "chk:saver:inv" not in {q["key"] for q in c.get("/api/review").get_json()["checks"]}
        assert {t.description: t for t in st.all_transactions()}["TRANSFER IN"].category == "Transfers"


class TestAnInvestmentFirmByName:
    def test_asked_once_per_destination_and_her_yes_is_a_rule(self, app):
        st = app.config["STORE"]
        rows = load(st, row(300.0, "QUESTRADE INC", merchant="Questrade Inc"),
                    row(250.0, "QUESTRADE INC", merchant="Questrade Inc", seq=1))
        assert all(t.category == "Transfers" for t in rows.values())
        with app.test_client() as c:
            asks = [q for q in c.get("/api/review").get_json()["checks"] if q["key"].startswith("chk:dest:")]
            assert len(asks) == 1
            assert asks[0]["pair"]["question"].startswith("Is ") and "where you save?" in asks[0]["pair"]["question"]
            r = c.post(f"/api/review/check/{asks[0]['key']}", json={"yes": True})
            assert r.status_code == 200
        assert all(t.category == "Saved" for t in st.all_transactions())
        assert "Saved" in st.destinations().values()

    def test_a_transfer_she_marked_saved_herself_stays(self, app):
        st = app.config["STORE"]
        rows = load(st, row(300.0, "TFR TO ACCT 9999"))
        tid = rows["TFR TO ACCT 9999"].fingerprint
        with app.test_client() as c:
            assert c.post(f"/api/transactions/{tid}/mark", json={"case": "saved"}).status_code == 200
        from finance.transfers import apply_transfer_matches
        apply_transfer_matches(st)
        assert st.get_transaction(tid).category == "Saved"
