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

# Also headerless and also five columns wide, so column count alone can't
# tell it from Wells Fargo: date, description, debit, credit, balance.
TD = """04/05/2026,UBER   *TRIP,17.31,,3581.38
04/04/2026,BEANFIELD FIBRE 1 L.P.,73.45,,3564.07
03/30/2026,PAYMENT - THANK YOU,,1047.86,3286.59
03/17/2026,WWW.HOSTELWORLD.COM,,3.03,2906.84
03/04/2026,"CURSOR, AI POWERED IDE",31.87,,1272.96
"""

WEALTHSIMPLE = """transaction_date,transaction_type,status,merchant,amount,currency,notes,category
2026-09-27,Purchase,Completed,Presto Fare/Sq5Sk6Qzkk,-3.30,CAD,,Public transit
2026-09-26,Purchase,Completed,Quantum Coffee,-10.17,CAD,,Coffee
2026-09-17,Payment,Completed,,205.06,CAD,,Uncategorized
2026-08-26,Purchase,Completed,Chipotle Online,-14.35,CAD,,Restaurants
2026-08-23,Purchase,Completed,Chipotle 5323,-14.35,CAD,,Restaurants
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
        assert r.format_key == "wells_fargo"

    def test_td_is_not_mistaken_for_wells_fargo(self):
        r = parse_csv(TD, "accountactivity.csv")
        assert r.format_key == "td_canada"
        assert r.skipped_rows == 0
        assert [t.amount for t in r.transactions] == [17.31, 73.45, -1047.86, -3.03, 31.87]
        assert r.transactions[4].description == "CURSOR, AI POWERED IDE"

    def test_wealthsimple(self):
        r = parse_csv(WEALTHSIMPLE, "credit-card-activities-2026-09-29.csv")
        assert r.format_key == "wealthsimple"
        assert r.transactions[0].amount == 3.30          # purchases flip positive
        payment = r.transactions[2]
        assert payment.amount == -205.06
        assert payment.description == "Payment"          # blank merchant falls back


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

    def test_repeat_downloads_land_in_one_account(self):
        """Browsers number repeat downloads; issuers stamp the export date."""
        a = parse_csv(TD, "accountactivity.csv")
        b = parse_csv(TD, "accountactivity (8).csv")
        assert a.account_id == b.account_id
        assert a.account_name == "TD Canada — Accountactivity"

        c = parse_csv(WEALTHSIMPLE, "credit-card-activities-2026-09-21.csv")
        d = parse_csv(WEALTHSIMPLE, "credit-card-activities-2026-09-29.csv")
        assert c.account_id == d.account_id


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


# Scotiabank's own export, as downloaded: three columns, the description headed
# "Details", and purchases written positive. The schema table had it as
# negative-for-purchases, which is a real convention for some of their exports
# and the opposite of this one.
SCOTIA_POSITIVE = """Date,Details,Amount
2025-03-19,QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY),19.21
2025-03-20,LONGO'S # 18 TORONTO TORONTO ON (APPLE PAY),66.92
2025-03-21,SCENE+ POINTS FOR CREDIT,-300.00
2025-03-23,PAYMENT FROM-*****10*6822,-1886.04
2025-03-23,BAR POMPETTE TORONTO ON (APPLE PAY),224.01
"""

# The mirror image: same layout, purchases negative, payment positive.
SCOTIA_NEGATIVE = """Date,Details,Amount
2025-03-19,QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY),-19.21
2025-03-20,LONGO'S # 18 TORONTO TORONTO ON (APPLE PAY),-66.92
2025-03-23,PAYMENT FROM-*****10*6822,1886.04
2025-03-23,BAR POMPETTE TORONTO ON (APPLE PAY),-224.01
"""


class TestDescriptionColumnFallback:
    """A schema naming a column the file lacks must not cost the description."""

    def test_details_column_is_read_when_the_schema_says_description(self):
        r = parse_csv(SCOTIA_POSITIVE, filename="all_transactions.csv")
        assert r.format_key == "scotiabank"
        descriptions = [t.description for t in r.transactions]
        assert "(no description)" not in descriptions
        assert descriptions[0].startswith("QUEEN'S CROSS FOOD HALL")

    def test_the_merchant_survives_the_round_trip(self):
        r = parse_csv(SCOTIA_POSITIVE, filename="all_transactions.csv")
        assert r.transactions[0].merchant == "Queen's Cross Food Hall"


class TestSignInferredFromThePayments:
    """The file decides which way round it is, not the schema table."""

    def test_purchases_stay_positive_when_the_export_writes_them_positive(self):
        r = parse_csv(SCOTIA_POSITIVE, filename="scotia.csv")
        by_desc = {t.description: t.amount for t in r.transactions}
        assert by_desc["QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY)"] == 19.21
        assert by_desc["PAYMENT FROM-*****10*6822"] == -1886.04
        assert by_desc["SCENE+ POINTS FOR CREDIT"] == -300.00

    def test_the_override_is_reported_rather_than_silent(self):
        r = parse_csv(SCOTIA_POSITIVE, filename="scotia.csv")
        assert any("opposite" in w for w in r.warnings), r.warnings

    def test_the_declared_sign_still_holds_for_the_other_direction(self):
        r = parse_csv(SCOTIA_NEGATIVE, filename="scotia.csv")
        by_desc = {t.description: t.amount for t in r.transactions}
        assert by_desc["QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY)"] == 19.21
        assert by_desc["PAYMENT FROM-*****10*6822"] == -1886.04
        assert not any("opposite" in w for w in r.warnings)

    def test_a_file_with_no_payment_row_keeps_the_declared_sign(self):
        from finance.ingest.csv_source import infer_sign
        rows = [("LONGO'S", 66.92), ("BAR POMPETTE", 224.01)]
        assert infer_sign(rows, -1) == (-1, None)

    def test_contradictory_payment_rows_are_not_trusted(self):
        """A chequing export has payments going both ways; it proves nothing."""
        from finance.ingest.csv_source import infer_sign
        rows = [("PAYMENT FROM-1234", -500.0), ("PAYMENT THANK YOU", 40.0),
                ("LONGO'S", 66.92)]
        assert infer_sign(rows, -1) == (-1, None)

    def test_a_wrongly_inverted_file_is_flagged_even_without_a_payment_row(self):
        no_payments = """Date,Details,Amount
2025-03-19,QUEEN'S CROSS FOOD HALL TORONTO ON,19.21
2025-03-20,LONGO'S # 18 TORONTO TORONTO ON,66.92
2025-03-23,BAR POMPETTE TORONTO ON,224.01
"""
        r = parse_csv(no_payments, filename="scotia.csv")
        # sign=-1 stands with no evidence against it, so every row reads as an
        # inflow -- which is exactly what the warning is for.
        assert all(t.amount < 0 for t in r.transactions)
        assert any("money coming in" in w for w in r.warnings), r.warnings

    def test_the_issuers_with_a_known_sign_are_unaffected(self):
        """The inference agrees with every schema it was checked against."""
        amex = parse_csv(AMEX, filename="amex.csv")
        chase = parse_csv(CHASE, filename="chase.csv")
        ws = parse_csv(WEALTHSIMPLE, filename="ws.csv")
        for r in (amex, chase, ws):
            assert not any("opposite" in w for w in r.warnings), r.warnings
        assert [t for t in amex.transactions if t.amount < 0][0].amount == -1200.00
        assert [t for t in chase.transactions if t.amount < 0][0].amount == -1200.00
        assert [t for t in ws.transactions if t.amount < 0][0].amount == -205.06


class TestWalletTags:
    """Tap-to-pay tags sit after the city, so they block the city stripping."""

    @pytest.mark.parametrize("raw,expected", [
        ("QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY)", "Queen's Cross Food Hall"),
        ("ZEN KYOTO 001 TORONTO ON (APPLE PAY)", "Zen Kyoto"),
        ("TST-CHAMBERLAIN'S PONY TORONTO ON (APPLE PAY)", "Chamberlain's Pony"),
        ("METRO 759 TORONTO ON (GOOGLE PAY)", "Metro"),
        # A trailing "CO" is read as Colorado by an older rule; documented
        # here so the wallet fix is not blamed for it.
        ("DINEEN COFFEE CO TORONTO ON (APPLE PAY)", "Dineen Coffee"),
    ])
    def test_the_tag_and_the_city_both_come_off(self, raw, expected):
        assert normalize_merchant(raw) == expected

    def test_a_two_word_city_is_still_stripped(self):
        assert normalize_merchant("UBER TRIP SAN FRANCISCO CA") == "Uber Trip"
        assert normalize_merchant("SQ *BLUE BOTTLE COFFEE OAKLAND CA") \
            == "Blue Bottle Coffee"

    def test_the_last_word_of_a_name_is_not_mistaken_for_a_city(self):
        """"FOOD HALL TORONTO ON" reads as a two-word city if nothing stops it."""
        assert normalize_merchant("PAGE ONE CAFE TORONTO ON") == "Page One Cafe"
        assert normalize_merchant("BAR POMPETTE TORONTO ON") == "Bar Pompette"


class TestLoyaltyRedemptions:
    """A credit booked as negative spending makes the month look cheaper."""

    @pytest.mark.parametrize("descriptor", [
        "SCENE+ POINTS FOR CREDIT",
        "SCENE+ TRAVEL CREDIT",
        "STATEMENT CREDIT",
        "AEROPLAN POINTS CREDIT",
        "CREDIT BAL REFUND",
    ])
    def test_a_redemption_is_not_spending(self, descriptor):
        from finance.categorize import NON_SPEND, categorize
        from finance.models import normalize_merchant
        category = categorize(normalize_merchant(descriptor), descriptor)[0]
        assert category in NON_SPEND, f"{descriptor} counted as {category}"

    def test_the_word_credit_alone_does_not_make_a_transfer(self):
        from finance.categorize import categorize
        assert categorize("Credit Suisse Coffee", "CREDIT SUISSE COFFEE")[0] != "Transfers"
