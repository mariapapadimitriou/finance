"""Putting statement rows into a test ledger.

The app had two ways in besides Plaid: uploading a file and loading the
bundled statements. Both were removed (C1), but the tests still need a ledger
with real-world rows in it, so these go through the same reader and pipeline
the endpoints did — straight into the client's store.
"""

from __future__ import annotations

from finance.ingest import parse_csv
from finance.pipeline import ingest


def _store(client):
    return client.application.config["STORE"]


def upload(client, content: str, name: str = "export.csv",
           account_name: str | None = None) -> dict:
    """One CSV file, reported the way the upload endpoint reported it."""
    result = ingest(_store(client),
                    parse_csv(content=content, filename=name,
                              account_name=account_name),
                    filename=name)
    return {"results": [result], "imported": result["imported"],
            "duplicates": result["duplicates"]}


def load_bundled(client_or_store, key: str = "scotiabank_amex") -> dict:
    """The owner's closed Scotiabank Amex, as the bundled button loaded it."""
    from seed_data.bundled import read

    st = (client_or_store if hasattr(client_or_store, "all_transactions")
          else _store(client_or_store))
    text, entry = read(key)
    result = parse_csv(content=text, filename=entry["file"],
                       account_name=entry["account_name"],
                       account_id=entry["account_id"])
    return ingest(st, result, filename=f"{entry['label']} (bundled)")


def add_fixed(client, name: str, amount: float, category: str = "Other") -> int:
    """A commitment as the old Income and commitments page saved it. That page
    and its endpoints went with THL-127; commitments already saved still
    count in the plan's arithmetic, so tests put them in the store directly."""
    return _store(client).add_fixed_cost(name, amount, category)


def set_plan(client, income: float | None = None, savings: float | None = None) -> None:
    """Take-home pay and the monthly saving goal, as the old plan page saved
    them (PUT /api/plan/setup, removed with the prototype Projections page).
    Home's Allowance still reads both, so tests put them in the store."""
    st = _store(client)
    if income is not None:
        st.set_setting("monthly_income", max(float(income), 0.0))
    if savings is not None:
        st.set_setting("savings_target", max(float(savings), 0.0))
