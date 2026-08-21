"""Dedupe, categorization, analytics, recurring detection and the savings rules."""

from datetime import date, timedelta

import pytest

from finance.analytics import (
    by_category,
    fixed_vs_discretionary,
    is_month_complete,
    last_complete_month,
    monthly_totals,
    summary,
)
from finance.categorize import apply_categories, categorize
from finance.dedupe import dedupe_batch, find_duplicate_charges, split_new
from finance.ingest import parse_csv
from finance.insights import detect_recurring, findings_summary, generate_findings
from finance.models import Transaction


def txn(date_str, desc, amount, account="card1", category=""):
    t = Transaction(date=date_str, description=desc, amount=amount, account_id=account)
    if category:
        t.category = category
    return t


def monthly_series(desc, amount, months, start_year=2025, start_month=1,
                   day=10, account="card1", amounts=None):
    """A charge on the same day each month, for building recurring fixtures."""
    out = []
    y, m = start_year, start_month
    for i in range(months):
        value = amounts[i] if amounts else amount
        out.append(txn(f"{y:04d}-{m:02d}-{day:02d}", desc, value, account))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ── Deduplication ────────────────────────────────────────────────────────────

class TestDedupe:
    def test_reimporting_the_same_file_adds_nothing(self):
        csv = """Date,Description,Card Member,Account #,Amount
07/14/2026,BLUE BOTTLE COFFEE,M P,-31004,6.40
07/15/2026,WHOLE FOODS MKT,M P,-31004,84.20
"""
        first = parse_csv(csv, "export.csv").transactions
        second = parse_csv(csv, "export.csv").transactions

        new, dupes = split_new(second, first)
        assert new == []
        assert len(dupes) == 2

    def test_overlapping_exports_only_add_the_new_rows(self):
        january = """Date,Description,Card Member,Account #,Amount
01/10/2026,BLUE BOTTLE COFFEE,M P,-31004,6.40
01/20/2026,WHOLE FOODS MKT,M P,-31004,84.20
"""
        # February's export re-delivers January and adds February.
        february = january + "02/05/2026,TRADER JOES,M P,-31004,52.10\n"

        existing = parse_csv(january, "jan.csv").transactions
        incoming = parse_csv(february, "feb.csv").transactions

        new, dupes = split_new(incoming, existing)
        assert len(new) == 1
        assert new[0].merchant == "Trader Joes"
        assert len(dupes) == 2

    def test_two_identical_coffees_same_day_are_both_kept(self):
        """The case naive fingerprinting gets wrong."""
        csv = """Date,Description,Card Member,Account #,Amount
07/14/2026,BLUE BOTTLE COFFEE,M P,-31004,6.40
07/14/2026,BLUE BOTTLE COFFEE,M P,-31004,6.40
"""
        rows = parse_csv(csv, "e.csv").transactions
        assert len(rows) == 2
        kept, dropped = dedupe_batch(rows)
        assert len(kept) == 2
        assert dropped == 0

    def test_a_settle_date_shift_is_treated_as_the_same_charge(self):
        existing = [txn("2026-07-14", "BLUE BOTTLE COFFEE", 6.40)]
        # Same charge, reported two days later by a later export.
        incoming = [txn("2026-07-16", "BLUE BOTTLE COFFEE", 6.40)]
        new, dupes = split_new(incoming, existing)
        assert new == []
        assert len(dupes) == 1

    def test_a_distant_repeat_purchase_is_not_a_duplicate(self):
        existing = [txn("2026-07-01", "BLUE BOTTLE COFFEE", 6.40)]
        incoming = [txn("2026-07-20", "BLUE BOTTLE COFFEE", 6.40)]
        new, dupes = split_new(incoming, existing)
        assert len(new) == 1

    def test_same_amount_different_merchants_never_merge(self):
        existing = [txn("2026-07-14", "BLUE BOTTLE COFFEE", 12.00)]
        incoming = [txn("2026-07-15", "CHIPOTLE", 12.00)]
        new, dupes = split_new(incoming, existing)
        assert len(new) == 1

    def test_different_cards_never_merge(self):
        existing = [txn("2026-07-14", "NETFLIX", 22.99, account="amex")]
        incoming = [txn("2026-07-15", "NETFLIX", 22.99, account="chase")]
        new, _ = split_new(incoming, existing)
        assert len(new) == 1

    def test_double_billing_is_reported_separately(self):
        rows = [
            txn("2026-07-14", "NOPA RESTAURANT", 96.40),
            txn("2026-07-14", "NOPA RESTAURANT", 96.40),
        ]
        found = find_duplicate_charges(rows)
        assert len(found) == 1
        assert found[0]["amount"] == 96.40


# ── Categorization ───────────────────────────────────────────────────────────

class TestCategorize:
    @pytest.mark.parametrize("merchant,expected", [
        ("Blue Bottle Coffee", "Coffee"),
        ("Whole Foods Mkt", "Groceries"),
        ("Doordash", "Food Delivery"),
        ("Uber Eats", "Food Delivery"),
        ("Uber Trip", "Transport"),
        ("Netflix", "Streaming"),
        ("Adobe Creative Cloud", "Software"),
        ("Shell Oil", "Gas & Fuel"),
        ("Equinox", "Fitness"),
        ("AT&T Wireless", "Phone & Internet"),
        ("Nytimes Digital", "News & Media"),
    ])
    def test_known_merchants(self, merchant, expected):
        assert categorize(merchant)[0] == expected

    def test_delivery_beats_rideshare_for_uber_eats(self):
        """Ordering matters: both rules match the word 'uber'."""
        assert categorize("Uber Eats")[0] == "Food Delivery"
        assert categorize("Uber Trip")[0] == "Transport"

    def test_interest_is_a_fee_not_a_merchant(self):
        assert categorize("Interest Charge On Purchases")[0] == "Fees & Interest"

    def test_unknown_falls_through_to_other(self):
        assert categorize("Zzyzx Widgets Ltd")[0] == "Other"

    def test_issuer_category_used_when_no_rule_matches(self):
        cat, src = categorize("Zzyzx Widgets", issuer_category="Restaurants")
        assert cat == "Dining"
        assert src == "issuer"

    def test_user_override_beats_every_rule(self):
        cat, src = categorize("Netflix", overrides={"netflix": "Entertainment"})
        assert cat == "Entertainment"
        assert src == "merchant_override"

    def test_apply_categories_respects_a_user_choice(self):
        t = txn("2026-07-14", "NETFLIX", 22.99)
        t.category, t.category_source = "Entertainment", "user"
        apply_categories([t])
        assert t.category == "Entertainment"


# ── Analytics ────────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_card_payments_are_excluded_from_spending(self):
        """A $1,200 card payment is not the month's biggest purchase."""
        rows = [
            txn("2026-07-01", "WHOLE FOODS", 84.20),
            txn("2026-07-25", "PAYMENT THANK YOU", -1200.00),
        ]
        apply_categories(rows)
        cats = {c["category"]: c["amount"] for c in by_category(rows, "2026-07")}
        assert "Transfers" not in cats
        assert cats["Groceries"] == 84.20

    def test_refunds_net_against_the_category(self):
        rows = [
            txn("2026-07-01", "TARGET", 120.00),
            txn("2026-07-08", "TARGET", -40.00),
        ]
        apply_categories(rows)
        cats = {c["category"]: c["amount"] for c in by_category(rows, "2026-07")}
        assert cats["Shopping"] == 80.00

    def test_monthly_totals_fill_gaps(self):
        rows = [txn("2026-01-05", "WHOLE FOODS", 50.0),
                txn("2026-04-05", "WHOLE FOODS", 50.0)]
        apply_categories(rows)
        months = [m["month"] for m in monthly_totals(rows)]
        assert months == ["2026-01", "2026-02", "2026-03", "2026-04"]

    def test_partial_month_is_detected(self):
        rows = [txn("2026-07-31", "X", 10.0), txn("2026-08-10", "X", 10.0)]
        assert is_month_complete(rows, "2026-07") is True
        assert is_month_complete(rows, "2026-08") is False
        assert last_complete_month(rows) == "2026-07"

    def test_discretionary_split(self):
        rows = [
            txn("2026-07-01", "PG&E ELECTRIC", 60.0),
            txn("2026-07-02", "NOPA RESTAURANT", 40.0),
        ]
        apply_categories(rows)
        split = fixed_vs_discretionary(rows, "2026-07")
        assert split["fixed"] == 60.0
        assert split["discretionary"] == 40.0

    def test_summary_handles_an_empty_ledger(self):
        assert summary([])["empty"] is True


# ── Recurring detection ──────────────────────────────────────────────────────

class TestRecurring:
    def test_monthly_subscription_is_found(self):
        rows = monthly_series("NETFLIX.COM", 22.99, 8)
        apply_categories(rows)
        found = detect_recurring(rows, as_of="2025-08-20")
        assert len(found) == 1
        assert found[0]["cadence"] == "monthly"
        assert found[0]["annual_cost"] == pytest.approx(275.88)

    def test_price_increase_is_detected_not_split_in_two(self):
        """A repricing must stay one subscription — the regression that matters."""
        amounts = [15.49] * 6 + [22.99] * 6
        rows = monthly_series("NETFLIX.COM", 0, 12, amounts=amounts)
        apply_categories(rows)
        found = detect_recurring(rows, as_of="2025-12-20")

        assert len(found) == 1
        change = found[0]["price_change"]
        assert change is not None
        assert change["direction"] == "increase"
        assert change["from"] == pytest.approx(15.49)
        assert change["to"] == pytest.approx(22.99)

    def test_irregular_purchases_are_not_recurring(self):
        rows = [
            txn("2025-01-03", "WHOLE FOODS", 84.20),
            txn("2025-01-19", "WHOLE FOODS", 32.10),
            txn("2025-02-11", "WHOLE FOODS", 156.80),
            txn("2025-03-02", "WHOLE FOODS", 61.40),
            txn("2025-03-27", "WHOLE FOODS", 98.15),
        ]
        apply_categories(rows)
        assert detect_recurring(rows) == []

    def test_two_charges_are_not_enough(self):
        rows = monthly_series("NETFLIX.COM", 22.99, 2)
        apply_categories(rows)
        assert detect_recurring(rows) == []

    def test_a_cancelled_subscription_is_marked_inactive(self):
        rows = monthly_series("HULU", 17.99, 5, start_year=2025, start_month=1)
        apply_categories(rows)
        found = detect_recurring(rows, as_of="2025-12-01")
        assert found[0]["active"] is False

    def test_annual_subscription(self):
        rows = [txn(f"{y}-03-15", "AMAZON PRIME MEMBERSHIP", 139.00)
                for y in (2023, 2024, 2025)]
        apply_categories(rows)
        found = detect_recurring(rows, as_of="2025-06-01")
        assert found and found[0]["cadence"] == "annual"

    def test_subscription_hidden_among_one_off_purchases(self):
        """Amazon Prime should be found even though Amazon also has orders."""
        rows = monthly_series("AMAZON PRIME*2K4LM AMZN.COM/BILL", 14.99, 10)
        rows += [
            txn("2025-02-03", "AMZN Mktp US*4H1", 84.20),
            txn("2025-04-11", "AMZN Mktp US*9K2", 31.50),
            txn("2025-07-22", "AMZN Mktp US*2L8", 129.99),
        ]
        apply_categories(rows)
        found = detect_recurring(rows, as_of="2025-10-20")
        prime = [r for r in found if "Prime" in r["merchant"]]
        assert prime and prime[0]["cadence"] == "monthly"


# ── Savings rules ────────────────────────────────────────────────────────────

class TestSavingsRules:
    def test_fees_produce_a_high_confidence_finding(self):
        rows = monthly_series("INTEREST CHARGE ON PURCHASES", 31.40, 12)
        rows += monthly_series("WHOLE FOODS MKT", 84.20, 12, day=3)
        apply_categories(rows)

        findings = generate_findings(rows)
        fees = [f for f in findings if f["kind"] == "fees"]
        assert fees
        assert fees[0]["confidence"] >= 0.9
        assert fees[0]["annual_saving"] == pytest.approx(376.8, rel=0.05)

    def test_price_creep_finding_reports_the_annual_delta(self):
        amounts = [15.49] * 6 + [22.99] * 6
        rows = monthly_series("NETFLIX.COM", 0, 12, amounts=amounts)
        apply_categories(rows)

        findings = generate_findings(rows)
        creep = [f for f in findings if f["kind"] == "price_creep"]
        assert creep
        assert creep[0]["annual_saving"] == pytest.approx(90.0, abs=0.01)

    def test_a_frequent_small_habit_is_surfaced(self):
        rows = []
        for month in range(1, 13):
            for day in range(1, 21):
                rows.append(txn(f"2025-{month:02d}-{day:02d}", "BLUE BOTTLE COFFEE", 6.40))
        apply_categories(rows)

        findings = generate_findings(rows)
        habits = [f for f in findings if f["kind"] == "habit"]
        assert habits
        # 20/month × $6.40 × 12 ≈ $1,536/yr; halving it is the stated assumption.
        assert habits[0]["annual_saving"] == pytest.approx(768, rel=0.1)
        assert "half" in habits[0]["assumption"].lower()

    def test_every_finding_carries_evidence_and_an_assumption(self):
        rows = monthly_series("NETFLIX.COM", 22.99, 12)
        rows += monthly_series("HULU", 17.99, 12, day=12)
        rows += monthly_series("DISNEY PLUS", 13.99, 12, day=15)
        rows += monthly_series("HBO MAX", 16.99, 12, day=18)
        rows += monthly_series("SPOTIFY USA", 11.99, 12, day=9)
        rows += monthly_series("INTEREST CHARGE ON PURCHASES", 30.0, 12, day=26)
        apply_categories(rows)

        findings = generate_findings(rows)
        assert findings
        for f in findings:
            assert f["annual_saving"] > 0
            assert f["assumption"], f"{f['kind']} has no stated assumption"
            assert 0 < f["confidence"] <= 1

    def test_overlapping_streaming_services_are_flagged(self):
        rows = []
        for i, (name, amount) in enumerate(
            [("NETFLIX.COM", 22.99), ("HULU", 17.99), ("DISNEY PLUS", 13.99),
             ("HBO MAX", 16.99)]
        ):
            rows += monthly_series(name, amount, 12, day=4 + i * 3)
        apply_categories(rows)

        findings = generate_findings(rows)
        overlap = [f for f in findings if f["kind"] == "overlap"]
        assert overlap
        # Conservative: only the cheapest of the stack is counted as droppable.
        assert overlap[0]["annual_saving"] == pytest.approx(13.99 * 12, abs=0.01)

    def test_dismissed_findings_are_withheld(self):
        rows = monthly_series("INTEREST CHARGE ON PURCHASES", 31.40, 12)
        apply_categories(rows)

        findings = generate_findings(rows)
        assert findings
        dismissed = {findings[0]["id"]}
        assert all(f["id"] not in dismissed for f in generate_findings(rows, dismissed))

    def test_no_findings_from_an_empty_ledger(self):
        assert generate_findings([]) == []

    def test_summary_totals_are_confidence_weighted(self):
        rows = monthly_series("INTEREST CHARGE ON PURCHASES", 31.40, 12)
        apply_categories(rows)
        s = findings_summary(generate_findings(rows))
        assert s["weighted_annual"] <= s["annual_total"]

    def test_findings_are_ranked_by_expected_value(self):
        rows = monthly_series("INTEREST CHARGE ON PURCHASES", 40.0, 12)
        rows += monthly_series("NOTION LABS", 10.0, 12, day=24)
        rows += monthly_series("EQUINOX", 215.0, 12, day=2)
        apply_categories(rows)

        findings = generate_findings(rows)
        scores = [f["annual_saving"] * max(f["confidence"], 0.3) for f in findings]
        assert scores == sorted(scores, reverse=True)
