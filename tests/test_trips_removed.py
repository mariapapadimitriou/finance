"""Trips are gone (C1): a charge a trip moved to Travel goes back.

A declared trip used to recategorize everything inside its dates as Travel,
with `category_source = 'trip'`. Nothing does that now, and a database from
before keeps no trace of it once opened — except a category set by hand.
"""

from finance.models import Transaction
from finance.store import Store


def _coffee(day: str, **kw) -> Transaction:
    return Transaction(date=day, description="MOS MOS COFFEE", merchant="Mos Mos Coffee",
                       amount=8.08, account_id="a", account_name="a", **kw)


def test_a_charge_a_trip_moved_goes_back_to_its_merchant(tmp_path):
    path = str(tmp_path / "t.db")
    st = Store(path)
    st.add_transactions([
        _coffee("2025-11-03", category="Travel", category_source="trip"),
        _coffee("2025-11-04", category="Travel", category_source="user"),
    ])

    rows = {t.date: t for t in Store(path).all_transactions()}
    assert rows["2025-11-03"].category == "Coffee"
    assert rows["2025-11-03"].category_source != "trip"
    # Yours stays yours.
    assert rows["2025-11-04"].category == "Travel"
    assert rows["2025-11-04"].category_source == "user"


def test_nothing_new_lands_in_travel_by_its_date(tmp_path):
    from finance.ingest.base import IngestResult
    from finance.pipeline import ingest

    st = Store(str(tmp_path / "t.db"))
    ingest(st, IngestResult(transactions=[_coffee("2025-11-05")]))
    assert [t.category for t in st.all_transactions()] == ["Coffee"]
