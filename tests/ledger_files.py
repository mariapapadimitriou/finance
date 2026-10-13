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
