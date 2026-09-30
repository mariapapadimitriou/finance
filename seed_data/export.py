"""Export the local ledger to the committed seed file, and load it back.

The export deliberately drops anything that is not the transaction itself.
Statement PDFs carry a name, a home address and a full account number; none of
that reaches the ledger, and the little provenance that does (the upload
filename) is stripped here too, since it is an opaque hash that means nothing
outside the machine that produced it.

    python -m seed_data.export            # write seed_data/transactions.json
    python -m seed_data.export --check    # report what would be written
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(HERE, "transactions.json")

# Only these travel. Anything else in the row stays local.
FIELDS = ("date", "post_date", "description", "merchant", "amount", "currency",
          "account_id", "account_name", "category", "category_source", "seq")


def export(db_path: str = "ledger.db", out: str = SEED_FILE) -> int:
    from finance.store import Store

    transactions = Store(db_path).all_transactions()
    rows = []
    for t in sorted(transactions, key=lambda x: (x.date, x.merchant)):
        row = {f: getattr(t, f) for f in FIELDS}
        row["source"] = "seed"
        # Keep the statement line number; drop the upload filename it came in.
        ref = (t.raw or {}).get("ref")
        if ref:
            row["ref"] = ref
        rows.append(row)

    # Trips travel with the ledger: without them a hosted instance would show
    # Travel spending it could not explain, and an empty Trips tab.
    trips = [
        {"name": t.name, "start_date": t.start_date, "end_date": t.end_date}
        for t in Store(db_path).trips()
    ]

    payload = {
        "note": "Transactions shipped with the app. Public by design — see "
                "seed_data/__init__.py.",
        "count": len(rows),
        "trips": trips,
        "transactions": rows,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return len(rows)


def load(store) -> int:
    """Load the seed file into an empty store. Never touches existing rows."""
    if not os.path.exists(SEED_FILE):
        return 0
    if store.all_transactions():
        return 0

    from finance.models import Transaction

    with open(SEED_FILE, encoding="utf-8") as fh:
        payload = json.load(fh)

    for t in payload.get("trips", []):
        store.add_trip(t["name"], t["start_date"], t["end_date"])

    rows = []
    for r in payload.get("transactions", []):
        rows.append(Transaction(
            date=r["date"],
            post_date=r.get("post_date"),
            description=r.get("description", ""),
            merchant=r.get("merchant", ""),
            amount=r["amount"],
            currency=r.get("currency", "CAD"),
            account_id=r.get("account_id", "seed"),
            account_name=r.get("account_name", ""),
            category=r.get("category", ""),
            category_source=r.get("category_source", "rule"),
            source="seed",
            seq=int(r.get("seq", 0) or 0),
            raw={"ref": r["ref"]} if r.get("ref") else {},
        ))
    return store.add_transactions(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="ledger.db")
    parser.add_argument("--check", action="store_true",
                        help="report what would be written, without writing")
    args = parser.parse_args()

    if args.check:
        from finance.store import Store
        rows = Store(args.db).all_transactions()
        print(f"{len(rows)} transactions would be exported")
        print(f"fields: {', '.join(FIELDS)}")
        return 0

    n = export(args.db)
    print(f"Wrote {n} transactions to {SEED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
