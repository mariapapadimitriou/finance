"""A bill paid from chequing sorts as spending by its payee (2026-11-15).

The product owner's utility payment wasn't sorted as spending: Plaid codes a
bill paid from a bank account LOAN_PAYMENTS_* or TRANSFER_OUT_*, and with no
account of hers at the other end it waited as an Unsorted transfer ("Saved
or spent? Tell us"). The bank's channel words ("BILL PAYMENT", "PAYMENT -",
"ONLINE BANKING PAYMENT") now come off, and the payee is sorted by the same
name patterns as any purchase. Card payments and loans stay transfers.
Demo data only."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.categorize import RULES_VERSION, bill_payee, categorize
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest, recategorize_all

DAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.mark.parametrize("desc,code,want", [
    ("BILL PAYMENT TORONTO HYDRO", "TRANSFER_OUT_ACCOUNT_TRANSFER", "Utilities"),
    ("BILL PAYMENT TORONTO HYDRO", "LOAN_PAYMENTS_OTHER_PAYMENT", "Utilities"),
    ("PAYMENT - HYDRO ONE", "LOAN_PAYMENTS", "Utilities"),
    ("ONLINE BANKING PAYMENT ENBRIDGE", "", "Utilities"),
    ("PRE-AUTHORIZED DEBIT ENBRIDGE GAS", "TRANSFER_OUT", "Utilities"),
    ("BILL PAYMENT CITY OF TORONTO WATER", "LOAN_PAYMENTS_OTHER_PAYMENT", "Utilities"),
    ("INTERNET BILL PAY 1234 ALECTRA UTILITIES", "TRANSFER_OUT_OTHER_TRANSFER_OUT", "Utilities"),
    ("BILL PAYMENT ROGERS", "TRANSFER_OUT_ACCOUNT_TRANSFER", "Phone & Internet"),
    ("PAYMENT - BELL CANADA", "TRANSFER_OUT_ACCOUNT_TRANSFER", "Phone & Internet"),
    ("ONLINE BANKING PAYMENT 0042 FIDO", "", "Phone & Internet"),
])
def test_a_bill_sorts_by_its_payee(desc, code, want):
    assert categorize(desc, desc, code) == (want, "rule")


@pytest.mark.parametrize("desc,code,want", [
    # A card payment, however it's worded, stays a transfer.
    ("BILL PAYMENT TD VISA", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", "Transfers"),
    ("BILL PAYMENT TD VISA", "LOAN_PAYMENTS_OTHER_PAYMENT", "Transfers"),
    ("BILL PAYMENT ROGERS MC 4417", "", "Transfers"),
    ("PAYMENT - THANK YOU", "", "Transfers"),
    # Money to her own account, and a payee Pearl can't name.
    ("TFR-TO 1234567", "TRANSFER_OUT_ACCOUNT_TRANSFER", "Transfers"),
    ("BILL PAYMENT XYZ CORP", "TRANSFER_OUT_ACCOUNT_TRANSFER", "Transfers"),
    # Even a Plaid code for hydro on a card payment: Plaid said card payment.
    ("BILL PAYMENT HYDRO ONE MC", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", "Transfers"),
])
def test_cards_own_accounts_and_unknown_payees_stay_transfers(desc, code, want):
    assert categorize(desc, desc, code)[0] == want


def test_only_a_bill_loses_its_words():
    assert bill_payee("BILL PAYMENT TORONTO HYDRO") == "TORONTO HYDRO"
    assert bill_payee("PAYMENT - BELL CANADA") == "BELL CANADA"
    assert bill_payee("PADDINGTON PUB") is None
    assert bill_payee("Water Street Cafe") is None
    # Bill-only words never sort a purchase.
    assert categorize("Water Street Cafe", "WATER STREET CAFE", "")[0] != "Utilities"


def row(desc, amount, code, account="chq"):
    return Transaction(date=DAY, description=desc, amount=amount, account_id=account,
                       account_name="TD Chequing ••4417", source="plaid",
                       raw={"account_type": "depository", "issuer_category": code})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "bills.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def listed(c):
    out = c.get("/api/transactions/list?limit=100").get_json()["transactions"]
    return {r["description"]: r for r in out}


def test_counts_as_spending_with_the_usual_chip(client):
    ingest(client.st, IngestResult([row("BILL PAYMENT TORONTO HYDRO", 142.18, "TRANSFER_OUT_ACCOUNT_TRANSFER"),
                                    row("BILL PAYMENT TD VISA", 600, "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")], "chq"))
    rows = listed(client)
    hydro = rows["BILL PAYMENT TORONTO HYDRO"]
    assert hydro["category"] == "Utilities" and hydro["counts"] == "spending"
    assert hydro["chip"]["label"] == "Utilities"
    # The card payment still waits to be matched or asked about, not spending.
    assert rows["BILL PAYMENT TD VISA"]["category"] in ("Transfers", "Unsorted transfers")


def test_rows_already_in_sort_again_once_and_hers_stay(client):
    st = client.st
    ingest(st, IngestResult([row("BILL PAYMENT TORONTO HYDRO", 142.18, "TRANSFER_OUT_ACCOUNT_TRANSFER"),
                             row("PAYMENT - BELL CANADA", 88.14, "TRANSFER_OUT_ACCOUNT_TRANSFER")], "chq"))
    by = {t.description: t.fingerprint for t in st.all_transactions()}
    # As the old rules left them: waiting as Unsorted transfers; and one she
    # sorted herself, which must stay hers.
    st.set_categories({by["BILL PAYMENT TORONTO HYDRO"]: ("Unsorted transfers", "transfer_match")})
    st.set_transaction_category(by["PAYMENT - BELL CANADA"], "Gifts & Charity")
    st.set_setting("categories_version", RULES_VERSION - 1)
    # What opening the app runs when the rules have moved on (api.py, plaid_link.py).
    recategorize_all(st)
    now = {t.description: t for t in st.all_transactions()}
    assert now["BILL PAYMENT TORONTO HYDRO"].category == "Utilities"
    assert now["PAYMENT - BELL CANADA"].category == "Gifts & Charity"
    assert now["PAYMENT - BELL CANADA"].category_source == "user"
