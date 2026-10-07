"""The Accounts page says which bank each account is from."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    from app import create_app
    app = create_app(str(tmp_path / "labels.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def plaid_rows(st, account_id, name, kind, subtype, item="item-td"):
    st.note_account(account_id, name=name, item_id=item, enabled=True,
                    account_type=kind, subtype=subtype)
    t = Transaction(date="2026-09-03", description="SOMETHING", amount=12,
                    account_id=account_id, account_name=name, source="plaid",
                    raw={"account_type": kind, "account_subtype": subtype})
    ingest(st, IngestResult(transactions=[t], account_id=account_id,
                            account_name=name, format_label="Plaid"))


def rows(c):
    return {a["account_id"]: a for a in c.get("/api/accounts").get_json()["accounts"]}


def test_connected_accounts_name_their_bank_kind_and_digits(client):
    st = client.application.config["STORE"]
    st.add_plaid_item("item-td", "access-x", institution="TD Bank")
    plaid_rows(st, "chq", "TD UNLIMITED CHEQUING ACCOUNT ••1234", "depository", "checking")
    plaid_rows(st, "visa", "TD Cash Back Visa ••5678", "credit", "credit card")
    plaid_rows(st, "tfsa", "Direct Investing TFSA ••9012", "investment", "tfsa")
    out = rows(client)
    assert (out["chq"]["institution"], out["chq"]["kind_label"], out["chq"]["mask"]) == \
        ("TD Bank", "Chequing", "1234")
    assert out["visa"]["kind_label"] == "Credit card" and out["visa"]["mask"] == "5678"
    assert out["tfsa"]["kind_label"] == "Investment"
    assert out["chq"]["imported_from"] is None


def test_an_account_switched_off_before_any_rows_still_names_its_bank(client):
    st = client.application.config["STORE"]
    st.add_plaid_item("item-td", "access-x", institution="TD Bank")
    st.note_account("sav", name="Every Day Savings ••4444", item_id="item-td",
                    enabled=False, account_type="depository", subtype="savings")
    out = rows(client)["sav"]
    assert (out["institution"], out["kind_label"], out["mask"]) == ("TD Bank", "Savings", "4444")


def test_a_statement_says_which_file_and_bank(client):
    st = client.application.config["STORE"]
    t = Transaction(date="2026-09-03", description="STARBUCKS", amount=5,
                    account_id="amex-1", account_name="Amex Cobalt", source="csv")
    ingest(st, IngestResult(transactions=[t], account_id="amex-1",
                            account_name="Amex Cobalt", format_label="American Express"),
           filename="amex-oct.csv")
    out = rows(client)["amex-1"]
    assert out["institution"] == "American Express"
    assert out["kind_label"] == "Card statement"
    assert out["imported_from"] == {"filename": "amex-oct.csv",
                                    "format_label": "American Express"}


def test_a_pdf_statement_names_the_bank_without_the_format(client):
    st = client.application.config["STORE"]
    t = Transaction(date="2026-09-03", description="X", amount=5,
                    account_id="scotia", account_name="Scotia Visa", source="pdf")
    ingest(st, IngestResult(transactions=[t], account_id="scotia",
                            format_label="Scotiabank statement (PDF)"), filename="s.pdf")
    assert rows(client)["scotia"]["institution"] == "Scotiabank"


def test_an_unknown_bank_is_left_empty(client):
    st = client.application.config["STORE"]
    st.add_plaid_item("item-x", "access-y", institution="")
    plaid_rows(st, "acct", "Chequing ••7777", "depository", "checking", item="item-x")
    t = Transaction(date="2026-09-03", description="X", amount=5,
                    account_id="generic", account_name="My card", source="csv")
    ingest(st, IngestResult(transactions=[t], account_id="generic",
                            format_label="CSV / statement export"), filename="x.csv")
    out = rows(client)
    assert out["acct"]["institution"] == "" and out["acct"]["kind_label"] == "Chequing"
    assert out["generic"]["institution"] == ""
