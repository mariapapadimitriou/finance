"""Finding a holiday in the ledger without being told the dates.

Declaring a trip is one of the most useful things available here and one of
the least likely to be done, because it means remembering dates and typing
them in. The evidence is already present: a card charged abroad carries the
conversion on the descriptor.

Detection is by *currency*, never by the place in a descriptor — a merchant
registered in Montreal may never have been visited, but a charge converted
from colónes really was made in colónes.
"""

from __future__ import annotations

import pytest

from finance import trip_finder
from finance.ingest import parse_csv
from finance.models import Transaction


def txn(date, desc, amount=10.0, currency="CAD", account="card"):
    return Transaction(date=date, description=desc, amount=amount,
                       account_id=account, account_name=account,
                       currency=currency, source="csv")


def abroad(date, n=3):
    return [txn(date, f"TIENDA {i} PUNTARENAS PUN AMT 5,000.00 CRC", 12.0)
            for i in range(n)]


def home(date, n=3):
    return [txn(date, f"MOS MOS COFFEE {i} TORONTO ON", 6.40) for i in range(n)]


class TestTheRealTrip:
    """The Costa Rica trip in the committed Scotiabank statements."""

    @pytest.fixture(scope="class")
    @classmethod
    def rows(cls):
        from pathlib import Path
        csv = (Path(__file__).resolve().parent.parent
               / "seed_data" / "scotiabank_amex_2025_2026.csv")
        return parse_csv(csv.read_text(), filename="s.csv",
                         account_name="Scotiabank", account_id="scotia").transactions

    def test_it_finds_exactly_one_trip(self, rows):
        assert len(trip_finder.suggest_trips(rows)) == 1

    def test_the_dates_are_the_real_ones(self, rows):
        [trip] = trip_finder.suggest_trips(rows)
        assert trip["start_date"] == "2026-03-26"
        assert trip["end_date"] == "2026-04-05"

    def test_it_is_named_after_somewhere_real(self, rows):
        """Not "Pun" — issuers append a truncated province after the town."""
        [trip] = trip_finder.suggest_trips(rows)
        assert trip["name"] == "Puntarenas"
        assert "San Jose" in trip["places"]
        assert not any(len(p) <= 3 for p in trip["places"])

    def test_it_reports_what_it_is_claiming(self, rows):
        [trip] = trip_finder.suggest_trips(rows)
        assert trip["charges"] == 51
        assert trip["total"] == pytest.approx(1797.93)
        assert trip["currencies"][0] == "CRC"

    def test_declaring_it_retires_the_suggestion(self, rows):
        declared = [{"start_date": "2026-03-20", "end_date": "2026-04-10"}]
        assert trip_finder.suggest_trips(rows, declared) == []


class TestWhatIsNotATrip:
    def test_a_single_foreign_charge_is_an_online_order(self):
        rows = home("2026-05-01") + [txn("2026-05-01", "STORE AMT 20.00 USD")]
        assert trip_finder.suggest_trips(rows) == []

    def test_two_days_abroad_is_below_the_bar(self):
        rows = abroad("2026-05-01") + abroad("2026-05-02")
        assert trip_finder.suggest_trips(rows) == []

    def test_a_home_descriptor_mentioning_a_place_is_not_a_trip(self):
        """The reason trips were never detected by location in the first place."""
        rows = [txn(f"2026-05-0{d}", "ZARA CANADA MONTREAL QC", 60.0)
                for d in range(1, 9)]
        assert trip_finder.suggest_trips(rows) == []

    def test_an_ordinary_month_at_home(self):
        rows = [t for d in range(1, 9) for t in home(f"2026-05-0{d}")]
        assert trip_finder.suggest_trips(rows) == []


class TestRunsOfDays:
    def test_a_quiet_travel_day_does_not_split_a_trip(self):
        """A day spent on a bus, buying nothing, is still inside the holiday."""
        rows = (abroad("2026-05-01") + abroad("2026-05-02")
                + abroad("2026-05-05") + abroad("2026-05-06"))
        [trip] = trip_finder.suggest_trips(rows)
        assert trip["start_date"] == "2026-05-01"
        assert trip["end_date"] == "2026-05-06"

    def test_two_separate_holidays_stay_separate(self):
        rows = []
        for d in ("01", "02", "03", "04"):
            rows += abroad(f"2026-05-{d}")
        for d in ("10", "11", "12", "13"):
            rows += abroad(f"2026-09-{d}")
        found = trip_finder.suggest_trips(rows)
        assert len(found) == 2
        assert found[0]["start_date"] == "2026-09-10"   # newest first

    def test_one_home_charge_inside_a_trip_is_tolerated(self):
        """A subscription renews mid-holiday; it does not end the holiday."""
        rows = []
        for d in ("01", "02", "03", "04"):
            rows += abroad(f"2026-05-{d}")
        rows.append(txn("2026-05-02", "NETFLIX.COM TORONTO ON", 20.99))
        [trip] = trip_finder.suggest_trips(rows)
        assert trip["days"] == 4


class TestCurrencyField:
    """Plaid reports the currency as a field rather than in the descriptor."""

    def test_a_foreign_currency_column_counts(self):
        rows = [txn(f"2026-06-0{d}", f"CAFE {i}", 9.0, currency="EUR")
                for d in range(1, 5) for i in range(3)]
        rows += [txn(f"2026-07-0{d}", f"SHOP {i}", 9.0) for d in range(1, 9)
                 for i in range(2)]
        [trip] = trip_finder.suggest_trips(rows)
        assert trip["currencies"] == ["EUR"]

    def test_the_home_currency_is_whatever_most_rows_use(self):
        rows = [txn("2026-06-01", "A", 9.0, currency="USD")] * 20
        assert trip_finder.home_currency(rows) == "USD"
