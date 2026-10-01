"""The Plaid adapter's payload mapping.

Plaid needs credentials to run, but its translation into our normalized model is
pure and can be tested against a recorded response shape — so the day the keys
arrive, the mapping is already known to be right.
"""

import pytest

from finance.ingest.plaid_source import (
    PlaidSource, group_plaid_transactions, map_plaid_transaction,
)

ACCOUNTS = {
    "acc_1": {"account_id": "acc_1", "name": "Sapphire Reserve",
              "official_name": "Chase Sapphire Reserve", "mask": "4471"},
    "acc_2": {"account_id": "acc_2", "name": "Platinum Card", "mask": "1004"},
}

TRANSACTIONS = [
    {
        "transaction_id": "tx_1",
        "account_id": "acc_1",
        "date": "2026-07-14",
        "authorized_date": "2026-07-13",
        "name": "SQ *BLUE BOTTLE COFFEE",
        "merchant_name": "Blue Bottle Coffee",
        "amount": 6.40,                       # Plaid: outflows are positive
        "iso_currency_code": "USD",
        "personal_finance_category": {"primary": "FOOD_AND_DRINK",
                                      "detailed": "FOOD_AND_DRINK_COFFEE"},
    },
    {
        "transaction_id": "tx_2",
        "account_id": "acc_1",
        "date": "2026-07-20",
        "name": "PAYMENT THANK YOU",
        "amount": -1200.00,                   # inflow
        "iso_currency_code": "USD",
        "personal_finance_category": {"primary": "TRANSFER_IN"},
    },
    {
        "transaction_id": "tx_3",
        "account_id": "acc_2",
        "date": "2026-07-15",
        "name": "NETFLIX.COM",
        "merchant_name": "Netflix",
        "amount": 22.99,
        "iso_currency_code": "USD",
        "personal_finance_category": {"primary": "ENTERTAINMENT"},
    },
]


class TestMapping:
    def test_outflow_stays_positive(self):
        """Plaid's convention already matches ours, so it must pass through."""
        t = map_plaid_transaction(TRANSACTIONS[0], ACCOUNTS)
        assert t.amount == 6.40

    def test_inflow_stays_negative(self):
        t = map_plaid_transaction(TRANSACTIONS[1], ACCOUNTS)
        assert t.amount == -1200.00

    def test_account_name_includes_the_mask(self):
        t = map_plaid_transaction(TRANSACTIONS[0], ACCOUNTS)
        assert t.account_name == "Chase Sapphire Reserve ••4471"

    def test_falls_back_to_the_short_account_name(self):
        t = map_plaid_transaction(TRANSACTIONS[2], ACCOUNTS)
        assert t.account_name == "Platinum Card ••1004"

    def test_merchant_name_is_preferred_over_the_raw_descriptor(self):
        t = map_plaid_transaction(TRANSACTIONS[0], ACCOUNTS)
        assert t.merchant == "Blue Bottle Coffee"

    def test_source_is_recorded(self):
        assert map_plaid_transaction(TRANSACTIONS[0], ACCOUNTS).source == "plaid"

    def test_plaid_category_is_carried_for_the_categorizer(self):
        t = map_plaid_transaction(TRANSACTIONS[0], ACCOUNTS)
        assert t.raw["issuer_category"] == "FOOD_AND_DRINK_COFFEE"

    def test_undated_rows_are_dropped_rather_than_crashing(self):
        assert map_plaid_transaction({"amount": 5.0, "name": "X"}, ACCOUNTS) is None

    def test_rows_without_an_amount_are_dropped(self):
        assert map_plaid_transaction({"date": "2026-07-14", "name": "X"}, ACCOUNTS) is None


class TestGrouping:
    def test_one_result_per_account(self):
        results = group_plaid_transactions(TRANSACTIONS, ACCOUNTS)
        assert len(results) == 2
        assert {r.account_id for r in results} == {"acc_1", "acc_2"}

    def test_results_match_the_csv_ingest_shape(self):
        """Plaid and CSV must be interchangeable to everything downstream."""
        r = group_plaid_transactions(TRANSACTIONS, ACCOUNTS)[0]
        assert r.format_key == "plaid"
        assert r.confidence == 1.0
        assert all(hasattr(t, 'fingerprint') for t in r.transactions)

    def test_identical_rows_get_distinct_fingerprints(self):
        dupe = [TRANSACTIONS[0], {**TRANSACTIONS[0], "transaction_id": "tx_9"}]
        r = group_plaid_transactions(dupe, ACCOUNTS)[0]
        assert len({t.fingerprint for t in r.transactions}) == 2


class TestStatus:
    def test_reports_unconfigured_with_actionable_steps(self, monkeypatch):
        monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
        monkeypatch.delenv("PLAID_SECRET", raising=False)

        st = PlaidSource().status()
        assert st.available is False
        assert st.setup_steps
        assert st.setup_url

    def test_fetch_refuses_clearly_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
        with pytest.raises(RuntimeError):
            PlaidSource().fetch(access_token="token")


class TestCardPaymentsAreNotSpending:
    """A payment to the card read as a purchase subtracts from the month.

    It is a negative amount, so landing it in a spending category does not
    merely mislabel it — it nets against real spending and makes the month
    look cheaper than it was. Of all the ways to get a category wrong, this is
    the one that flatters you, so it is worth more than one defence.
    """

    CARD = {"card": {"name": "TD Cash Back Visa", "type": "credit",
                     "subtype": "credit card", "mask": "4242"}}

    def _row(self, name, pfc, amount, accounts=None):
        from finance.categorize import apply_categories
        from finance.ingest.plaid_source import map_plaid_transaction
        raw = {
            "transaction_id": "x", "date": "2026-05-01", "name": name,
            "amount": amount, "account_id": "card",
            "personal_finance_category": (
                {"detailed": pfc, "primary": pfc.split("_")[0]} if pfc else None),
        }
        t = map_plaid_transaction(raw, accounts or self.CARD)
        apply_categories([t])
        return t

    @pytest.mark.parametrize("descriptor", [
        "PAYMENT - THANK YOU",
        "Payment Thank You-Mobile",
        "ONLINE BANKING PAYMENT",
        "AUTOMATIC PAYMENT - THANK YOU",
        "TD VISA PREAUTH PYMT",
        "CAPITAL ONE MOBILE PYMT",
        "CREDIT CARD PAYMENT",
    ])
    def test_plaids_own_code_settles_it(self, descriptor):
        from finance.categorize import NON_SPEND
        t = self._row(descriptor, "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", -500.00)
        assert t.category == "Transfers", f"{descriptor} -> {t.category}"
        assert t.category in NON_SPEND

    def test_a_transfer_in_is_not_spending_either(self):
        t = self._row("Wealthsimple", "TRANSFER_IN_ACCOUNT_TRANSFER", -200.00)
        assert t.category == "Transfers"

    def test_an_unrecognized_inflow_on_a_card_is_not_spending(self):
        """The backstop: a bank whose wording nothing here has ever seen."""
        t = self._row("ZZQ BILL PAY REF 88812", "", -412.00)
        assert t.category == "Transfers"
        assert t.category_source == "card_inflow"

    def test_a_refund_still_nets_against_its_own_category(self):
        """Returning a coffee is not a card payment; it belongs to Coffee."""
        t = self._row("STARBUCKS STORE 08812", "FOOD_AND_DRINK_COFFEE", -6.40)
        assert t.category == "Coffee"
        assert t.amount == -6.40

    def test_an_ordinary_purchase_is_untouched(self):
        t = self._row("UBER TRIP", "TRANSPORTATION_TAXI", 24.10)
        assert t.category == "Transport"

    def test_the_backstop_leaves_other_account_types_alone(self):
        """An unrecognized outflow on a chequing account may be real spending."""
        chequing = {"card": {"name": "TD Chequing", "type": "depository",
                             "subtype": "checking", "mask": "1111"}}
        t = self._row("ZZQ SOMETHING", "", -412.00, accounts=chequing)
        assert t.category == "Other"

    def test_payments_do_not_reduce_the_spending_total(self):
        """The whole point, measured the way the app measures it."""
        from finance.categorize import NON_SPEND, apply_categories
        from finance.ingest.plaid_source import map_plaid_transaction
        rows = []
        for i, (name, pfc, amt) in enumerate([
            ("UBER TRIP", "TRANSPORTATION_TAXI", 24.10),
            ("STARBUCKS", "FOOD_AND_DRINK_COFFEE", 6.40),
            ("TD VISA PREAUTH PYMT", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", -500.00),
            ("ZZQ MYSTERY PAYMENT", "", -300.00),
        ]):
            rows.append(map_plaid_transaction({
                "transaction_id": f"t{i}", "date": "2026-05-01", "name": name,
                "amount": amt, "account_id": "card",
                "personal_finance_category": (
                    {"detailed": pfc, "primary": pfc.split("_")[0]} if pfc else None),
            }, self.CARD))
        apply_categories(rows)
        spend = sum(t.amount for t in rows if t.category not in NON_SPEND)
        assert spend == 30.50          # not 30.50 - 800.00
