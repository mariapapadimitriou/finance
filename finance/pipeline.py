"""The import pipeline: source → dedupe → categorize → store.

One function so every ingestion path (CSV upload, Plaid sync, the sample-data
loader) goes through identical normalization and produces identical reporting.
"""

from __future__ import annotations

from . import manual
from .categorize import apply_categories
from .dedupe import dedupe_batch, split_new
from .ingest.base import IngestResult
from .store import Store
from .trips import apply_trips


def ingest(store: Store, result: IngestResult, filename: str = "") -> dict:
    """Persist one ingestion result, returning what happened."""
    batch, self_dupes = dedupe_batch(result.transactions)

    existing = store.all_transactions()
    new, dupes = split_new(batch, existing)

    apply_categories(new, store.overrides())
    # Declared trips outrank the merchant rules: a restaurant on holiday is
    # travel spending, not dining.
    apply_trips(new, store.trips())

    # A row typed in by hand was a placeholder for a charge that hadn't posted.
    # Now it has, so the statement's version replaces it — carrying across the
    # only thing the placeholder knew better, a category set by hand.
    replaced = manual.supersedes(new, existing)
    for imported, placeholder in replaced:
        if placeholder.category_source == "user":
            imported.category = placeholder.category
            imported.category_source = "user"
        store.delete_transaction(placeholder.fingerprint)

    inserted = store.add_transactions(new)

    duplicate_count = len(dupes) + self_dupes
    store.log_import(filename or "upload.csv", result, inserted, duplicate_count)

    return {
        **result.to_dict(),
        "filename": filename,
        "imported": inserted,
        "duplicates": duplicate_count,
        "replaced_manual": len(replaced),
        "date_range": (
            [min(t.date for t in new), max(t.date for t in new)] if new else None
        ),
    }


def recategorize_all(store: Store) -> int:
    """Re-run categorization over the whole ledger after rules or overrides change.

    User-set categories survive; everything else is recomputed.
    """
    transactions = store.all_transactions()
    overrides = store.overrides()
    apply_categories(transactions, overrides)
    apply_trips(transactions, store.trips())

    updated = 0
    with store.conn() as c:
        for t in transactions:
            cur = c.execute(
                """UPDATE transactions SET category = ?, category_source = ?
                   WHERE id = ? AND category_source != 'user'""",
                (t.category, t.category_source, t.fingerprint),
            )
            updated += cur.rowcount
    return updated
