"""CSV parsing: format detection, sign conventions, and messy real-world input."""

import pytest

from finance.ingest import parse_csv
from finance.models import normalize_merchant, parse_amount, parse_date

AMEX = """Date,Description,Card Member,Account #,Amount
07/14/2026,SQ *BLUE BOTTLE COFFEE OAKLAND CA,M P,-31004,6.40
07/15/2026,NETFLIX.COM 866-579-7172 CA,M P,-31004,22.99
07/16/2026,PAYMENT THANK YOU,M P,-31004,-1200.00
"""

CHASE = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
07/14/2026,07/16/2026,STARBUCKS STORE 08812,Food & Drink,Sale,-6.40,
07/15/2026,07/17/2026,UBER TRIP SAN FRANCISCO CA,Travel,Sale,-24.10,
07/20/2026,07/20/2026,Payment Thank You - Web,,Payment,1200.00,
"""

CAPITAL_ONE = """Transaction Date,Posted Date,Card No.,Description,Category,Debit,Credit
2026-07-14,2026-07-16,7781,SHELL OIL 57444103,Gas,48.20,
2026-07-15,2026-07-17,7781,COMCAST CALIFORNIA,Utilities,89.99,
2026-07-18,2026-07-19,7781,REFUND - RETURNED ITEM,Merchandise,,32.50
"""

CITI = """Status,Date,Description,Debit,Credit
Cleared,07/14/2026,TRADER JOES #178,64.20,
Cleared,07/16/2026,STATEMENT CREDIT,,15.00
"""

DISCOVER = """Trans. Date,Post Date,Description,Amount,Category
07/14/2026,07/15/2026,WHOLE FOODS MKT 10229,84.31,Supermarkets
07/16/2026,07/17/2026,AMAZON.COM*RT4XY,29.99,Merchandise
"""

# No header row at all — several banks still export this way.
WELLS_FARGO = """07/14/2026,-42.10,*,,SAFEWAY STORE 1842
07/15/2026,-8.75,*,,PEETS COFFEE 0231
"""


class TestFormatDetection:
    def test_amex(self):
        r = parse_csv(AMEX, "amex.csv")
        assert r.format_key == "amex"
        assert r.confidence >= 0.6
        assert len(r.transactions) == 3

    def test_chase(self):
        r = parse_csv(CHASE, "chase.csv")
        assert r.format_key == "chase"
        assert len(r.transactions) == 3

    def test_capital_one(self):
        r = parse_csv(CAPITAL_ONE, "capone.csv")
        assert r.format_key == "capital_one"
        assert len(r.transactions) == 3

    def test_citi(self):
        r = parse_csv(CITI, "citi.csv")
        assert r.format_key == "citi"

    def test_discover(self):
        r = parse_csv(DISCOVER, "discover.csv")
        assert r.format_key == "discover"

    def test_headerless_is_still_parsed(self):
        r = parse_csv(WELLS_FARGO, "wf.csv")
        assert len(r.transactions) == 2
        assert r.transactions[0].description == "SAFEWAY STORE 1842"


class TestSignConventions:
    """Every issuer must end up positive-for-spending regardless of its export."""

    def test_amex_charges_stay_positive(self):
        r = parse_csv(AMEX, "amex.csv")
        coffee = next(t for t in r.transactions if "BLUE BOTTLE" in t.description)
        assert coffee.amount == 6.40

    def test_amex_payment_is_negative(self):
        r = parse_csv(AMEX, "amex.csv")
        payment = next(t for t in r.transactions if "PAYMENT" in t.description)
        assert payment.amount == -1200.00

    def test_chase_purchases_are_flipped_positive(self):
        r = parse_csv(CHASE, "chase.csv")
        coffee = next(t for t in r.transactions if "STARBUCKS" in t.description)
        assert coffee.amount == 6.40

    def test_chase_payment_is_flipped_negative(self):
        r = parse_csv(CHASE, "chase.csv")
        payment = next(t for t in r.transactions if "Payment" in t.description)
        assert payment.amount == -1200.00

    def test_capital_one_debit_column_is_spend(self):
        r = parse_csv(CAPITAL_ONE, "capone.csv")
        gas = next(t for t in r.transactions if "SHELL" in t.description)
        assert gas.amount == 48.20

    def test_capital_one_credit_column_is_inflow(self):
        r = parse_csv(CAPITAL_ONE, "capone.csv")
        refund = next(t for t in r.transactions if "REFUND" in t.description)
        assert refund.amount == -32.50

    def test_same_purchase_same_sign_across_three_issuers(self):
        """The whole point of normalization: $6.40 of coffee is $6.40 everywhere."""
        amex = parse_csv(AMEX, "a.csv").transactions[0].amount
        chase = parse_csv(CHASE, "c.csv").transactions[0].amount
        assert amex == chase == 6.40


class TestAccountResolution:
    def test_card_number_becomes_account_identity(self):
        r = parse_csv(CAPITAL_ONE, "capone.csv")
        assert "7781" in r.account_name
        assert r.account_id == "capital_one_7781"

    def test_explicit_name_wins(self):
        r = parse_csv(AMEX, "amex.csv", account_name="My Platinum")
        assert r.account_name == "My Platinum"

    def test_same_card_two_exports_share_an_account_id(self):
        a = parse_csv(CAPITAL_ONE, "jan.csv")
        b = parse_csv(CAPITAL_ONE, "feb.csv")
        assert a.account_id == b.account_id


class TestMessyInput:
    def test_preamble_lines_are_skipped(self):
        messy = 'Account Summary Export\nGenerated 2026-07-20\n\n' + AMEX
        r = parse_csv(messy, "messy.csv")
        assert len(r.transactions) == 3

    def test_unparseable_rows_are_skipped_not_fatal(self):
        broken = AMEX + "not-a-date,GARBAGE,,,,\n"
        r = parse_csv(broken, "broken.csv")
        assert len(r.transactions) == 3
        assert r.skipped_rows == 1
        assert r.warnings

    def test_empty_file(self):
        r = parse_csv("", "empty.csv")
        assert r.transactions == []

    def test_semicolon_delimiter(self):
        semi = AMEX.replace(",", ";")
        r = parse_csv(semi, "euro.csv")
        assert len(r.transactions) == 3

    def test_bom_is_stripped(self):
        r = parse_csv("﻿" + AMEX, "bom.csv")
        assert r.format_key == "amex"


class TestParseHelpers:
    @pytest.mark.parametrize("raw,expected", [
        ("07/14/2026", "2026-07-14"),
        ("2026-07-14", "2026-07-14"),
        ("14-Jul-2026", "2026-07-14"),
        ("Jul 14, 2026", "2026-07-14"),
        ("20260714", "2026-07-14"),
        ("2026-07-14T09:31:00Z", "2026-07-14"),
        ("garbage", None),
        ("", None),
    ])
    def test_dates(self, raw, expected):
        assert parse_date(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("$1,234.56", 1234.56),
        ("(45.00)", -45.00),          # accounting-style negative
        ("-45.00", -45.00),
        ("1.234,56", 1234.56),        # European decimal comma
        ("USD 82.10", 82.10),
        ("", None),
        ("--", None),
    ])
    def test_amounts(self, raw, expected):
        assert parse_amount(raw) == expected


class TestMerchantNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("SQ *BLUE BOTTLE COFFEE 4471 OAKLAND CA", "Blue Bottle Coffee"),
        ("TST* NOPA RESTAURANT SAN FRANCISCO CA", "Nopa Restaurant"),
        ("NETFLIX.COM 866-579-7172 CA", "Netflix"),
        ("HULU 877-8244858 CA", "Hulu"),
        ("STATE FARM INSURANCE 800-STATEFARM", "State Farm Insurance"),
        ("STARBUCKS STORE 08812 SAN FRANCISCO CA", "Starbucks"),
        ("AMZN Mktp US*RT4XY9012 AMZN.COM/BILL WA", "Amazon"),
        ("AMAZON.COM*M12QR4 SEATTLE WA", "Amazon"),
        ("AMAZON PRIME*2K4LM AMZN.COM/BILL WA", "Amazon Prime"),
    ])
    def test_descriptors_collapse_to_clean_names(self, raw, expected):
        assert normalize_merchant(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        # The city-stripping pattern used to reach back over the last word of
        # the business name, taking "BAR" and "HOUSE" with the city — and with
        # them the only clue to what the merchant actually is.
        ("ZEITGEIST BAR SAN FRANCISCO CA", "Zeitgeist Bar"),
        ("DOORDASH*THAI HOUSE SAN FRANCISCO CA", "Doordash Thai House"),
        ("TRADER JOE'S #178 SAN FRANCISCO CA", "Trader Joe's"),
        ("PEET'S COFFEE 0231 BERKELEY CA", "Peet's Coffee"),
    ])
    def test_city_stripping_leaves_the_business_name_intact(self, raw, expected):
        assert normalize_merchant(raw) == expected

    def test_a_bar_is_still_categorized_as_a_bar(self):
        """The normalization bug above silently broke this categorization."""
        from finance.categorize import categorize
        raw = "ZEITGEIST BAR SAN FRANCISCO CA"
        assert categorize(normalize_merchant(raw), raw)[0] == "Alcohol & Bars"

    def test_same_merchant_across_processors_groups_together(self):
        a = normalize_merchant("SQ *BLUE BOTTLE COFFEE 4471 OAKLAND CA")
        b = normalize_merchant("BLUE BOTTLE COFFEE #221 SAN FRANCISCO CA")
        assert a == b

    def test_never_returns_empty(self):
        assert normalize_merchant("") == "Unknown"
        assert normalize_merchant("###") == "Unknown"
