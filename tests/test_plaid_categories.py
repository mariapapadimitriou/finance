"""Plaid's own categories, mapped properly — and chequing rows that count right.

Most of a connected account used to land in Other: only the first word of
Plaid's code was tried, and "food", "general", "rent" match nothing.
"""

from __future__ import annotations

import pytest

from finance import plaid_link, secrets_box
from finance.analytics import counts_as_spending
from finance.categorize import RULES_VERSION, apply_categories, categorize
from finance.ingest.plaid_source import group_plaid_transactions
from finance.store import Store


@pytest.mark.parametrize("code,expected", [
    ("FOOD_AND_DRINK_RESTAURANT", "Dining"),
    ("FOOD_AND_DRINK_FAST_FOOD", "Dining"),
    ("FOOD_AND_DRINK_GROCERIES", "Groceries"),
    ("FOOD_AND_DRINK_COFFEE", "Coffee"),
    ("FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR", "Alcohol & Bars"),
    ("GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES", "Shopping"),
    ("GENERAL_MERCHANDISE_ELECTRONICS", "Shopping"),
    ("GENERAL_MERCHANDISE_PET_SUPPLIES", "Pets"),
    ("GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES", "Gifts & Charity"),
    ("HOME_IMPROVEMENT_HARDWARE", "Home"),
    ("MEDICAL_PHARMACIES_AND_SUPPLEMENTS", "Health"),
    ("MEDICAL_VETERINARY_SERVICES", "Pets"),
    ("PERSONAL_CARE_HAIR_AND_BEAUTY", "Personal Care"),
    ("PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS", "Fitness"),
    ("ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS", "Entertainment"),
    ("ENTERTAINMENT_MUSIC_AND_AUDIO", "Streaming"),
    ("TRANSPORTATION_TAXIS_AND_RIDE_SHARES", "Transport"),
    ("TRANSPORTATION_GAS", "Gas & Fuel"),
    ("TRAVEL_FLIGHTS", "Travel"),
    ("TRAVEL_LODGING", "Lodging"),
    ("RENT_AND_UTILITIES_RENT", "Rent & Housing"),
    ("RENT_AND_UTILITIES_TELEPHONE", "Phone & Internet"),
    ("RENT_AND_UTILITIES_INTERNET_AND_CABLE", "Phone & Internet"),
    ("RENT_AND_UTILITIES_GAS_AND_ELECTRICITY", "Utilities"),
    ("GENERAL_SERVICES_INSURANCE", "Insurance"),
    ("GENERAL_SERVICES_EDUCATION", "Education"),
    ("GENERAL_SERVICES_AUTOMOTIVE", "Transport"),
    ("GENERAL_SERVICES_CONSULTING_AND_LEGAL", "Other"),
    ("GOVERNMENT_AND_NON_PROFIT_DONATIONS", "Gifts & Charity"),
    ("GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT", "Taxes"),
    ("BANK_FEES_OVERDRAFT_FEES", "Fees & Interest"),
    ("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", "Transfers"),
    ("LOAN_PAYMENTS_MORTGAGE_PAYMENT", "Rent & Housing"),
    ("LOAN_PAYMENTS_CAR_PAYMENT", "Transport"),
    ("LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT", "Transfers"),
    ("INCOME_WAGES", "Income"),
    ("INCOME_INTEREST_EARNED", "Income"),
    ("TRANSFER_IN_DEPOSIT", "Transfers"),
    ("TRANSFER_OUT_SAVINGS", "Transfers"),
    ("TRANSFER_OUT_OTHER_TRANSFER_OUT", "Transfers"),
    ("TRANSFER_OUT_WITHDRAWAL", "Cash & ATM"),
    ("FOOD_AND_DRINK", "Dining"),                 # a bare primary
])
def test_a_plaid_code_maps_to_its_category(code, expected):
    assert categorize("", "", code)[0] == expected


def test_a_merchant_rule_still_beats_plaids_guess():
    # Plaid calls Netflix entertainment; our rule knows it is streaming.
    assert categorize("NETFLIX.COM", "", "ENTERTAINMENT_TV_AND_MOVIES")[0] == "Streaming"


def test_your_own_rule_beats_everything():
    assert categorize("LOCAL SPOT", "", "FOOD_AND_DRINK_RESTAURANT",
                      {"local spot": "Coffee"}) == ("Coffee", "merchant_override")


def test_money_moving_between_your_accounts_is_never_spending():
    assert categorize("STARBUCKS PAYMENT", "", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")[0] == "Transfers"
    assert categorize("PAYROLL ACME", "", "INCOME_WAGES")[0] == "Income"


ACCOUNTS = {"chq": {"account_id": "chq", "name": "Everyday Chequing", "mask": "1111",
                    "type": "depository", "subtype": "checking"}}


def row(tid, name, amount, code):
    return {"transaction_id": tid, "date": "2026-09-10", "name": name,
            "amount": amount, "account_id": "chq", "iso_currency_code": "CAD",
            "personal_finance_category": {"primary": code.split("_")[0],
                                          "detailed": code}}


def test_a_chequing_account_sorts_into_spending_and_not_spending():
    items = [
        row("p", "ACME CORP PAYROLL", -2600.0, "INCOME_WAGES"),
        row("e", "SEND E-TFR ***ABC", 80.0, "TRANSFER_OUT_OTHER_TRANSFER_OUT"),
        row("c", "TD VISA PAYMENT", 900.0, "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"),
        row("d", "THE KEG STEAKHOUSE", 64.0, "FOOD_AND_DRINK_RESTAURANT"),
        row("a", "ATM WITHDRAWAL", 100.0, "TRANSFER_OUT_WITHDRAWAL"),
    ]
    txns = [t for r in group_plaid_transactions(items, ACCOUNTS) for t in r.transactions]
    apply_categories(txns)
    by = {t.raw["plaid_id"]: t for t in txns}
    assert by["p"].category == "Income"
    assert by["e"].category == "Transfers"
    assert by["c"].category == "Transfers"
    assert by["d"].category == "Dining"
    assert by["a"].category == "Cash & ATM"
    assert counts_as_spending(by["d"])
    for k in ("p", "e", "c"):
        assert not counts_as_spending(by[k])


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


def test_the_next_sync_sorts_the_ledger_once_and_keeps_your_choices(
        tmp_path, monkeypatch):
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    store = Store(str(tmp_path / "s.db"))
    store.add_plaid_item("item-1", "tok", "TD")

    class Fake:
        def transactions_sync(self, request):
            return _Resp({"accounts": [{"account_id": "card", "name": "Visa",
                                        "type": "credit", "subtype": "credit card"}],
                          "added": [], "modified": [], "removed": [],
                          "has_more": False, "next_cursor": "c"})

    monkeypatch.setattr(plaid_link, "_client", lambda: Fake())
    monkeypatch.setattr(plaid_link, "configured", lambda: True)

    # Two rows sorted under the old rules: one left in Other, one you chose.
    from finance.ingest import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    a = Transaction(date="2026-09-01", description="CORNER BISTRO", amount=40.0,
                    account_id="card", source="plaid",
                    raw={"issuer_category": "FOOD_AND_DRINK_RESTAURANT",
                         "account_type": "credit"})
    b = Transaction(date="2026-09-02", description="MYSTERY SHOP", amount=20.0,
                    account_id="card", source="plaid",
                    raw={"issuer_category": "GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE",
                         "account_type": "credit"})
    ingest(store, IngestResult(transactions=[a, b], account_id="card", account_name="Visa"))
    with store.conn() as c:
        c.execute("UPDATE transactions SET category = 'Other', category_source = 'rule'")
        c.execute("UPDATE transactions SET category = 'Gifts & Charity', "
                  "category_source = 'user' WHERE description = 'MYSTERY SHOP'")

    plaid_link.sync_all(store)
    cats = {t.description: t.category for t in store.all_transactions()}
    assert cats == {"CORNER BISTRO": "Dining", "MYSTERY SHOP": "Gifts & Charity"}
    assert store.setting("categories_version") == str(RULES_VERSION)
