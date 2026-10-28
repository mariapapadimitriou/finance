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
from .transfers import apply_transfer_matches, migrate_overrides


def ingest(store: Store, result: IngestResult, filename: str = "",
           existing: list | None = None, settle: bool = True) -> dict:
    """Persist one ingestion result, returning what happened.

    `existing` is the ledger as already loaded, and `settle=False` leaves the
    across-the-ledger work (transfers, duplicates) to the caller:
    `ingest_many` loads the ledger once and settles once for a whole sync,
    rather than once per account (each load reads every row from the
    database, which on a hosted one is metered).
    """
    batch, self_dupes = dedupe_batch(result.transactions)

    if existing is None:
        existing = store.all_transactions()
    new, dupes = split_new(batch, existing)

    apply_categories(new, store.overrides())

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
    possible = 0
    if inserted and settle:
        possible = _settle(store)

    duplicate_count = len(dupes) + self_dupes
    store.log_import(filename or "upload.csv", result, inserted, duplicate_count)

    return {
        **result.to_dict(),
        "filename": filename,
        "imported": inserted,
        "duplicates": duplicate_count,
        "possible_duplicates": possible,
        "replaced_manual": len(replaced),
        "date_range": (
            [min(t.date for t in new), max(t.date for t in new)] if new else None
        ),
    }


def _settle(store: Store) -> int:
    """What new rows change across the ledger. Returns possible duplicates."""
    # A new arrival can be the other end of a transfer already here, and a
    # new departure may have its other end here already.
    classify_ledger(store)
    # The same purchase from a second source (a statement file beside the
    # bank connection, a card linked twice, a pending row whose posted
    # twin never named it) is asked about, not merged (THL-165). Exact
    # repeats were skipped above and only counted in the import log.
    from .duplicates import scan
    return scan(store)


def ingest_many(store: Store, results: list[IngestResult], filename: str = "") -> int:
    """Several accounts' rows at once (one bank's sync): the ledger is loaded
    once and settled once. Returns how many rows were added."""
    if not results:
        return 0
    existing = store.all_transactions()
    imported = 0
    for result in results:
        imported += ingest(store, result, filename=filename, existing=existing,
                           settle=False)["imported"]
    if imported:
        _settle(store)
    return imported


def recategorize_all(store: Store) -> int:
    """Re-run categorization over the whole ledger after rules or overrides change.

    User-set categories survive; everything else is recomputed.
    """
    migrate_overrides(store)
    transactions = store.all_transactions()
    overrides = store.overrides()
    apply_categories(transactions, overrides)

    updated = 0
    with store.conn() as c:
        for t in transactions:
            cur = c.execute(
                """UPDATE transactions SET category = ?, category_source = ?
                   WHERE id = ? AND category_source != 'user'""",
                (t.category, t.category_source, t.fingerprint),
            )
            updated += cur.rowcount
    # The rules just put every transfer back to plain Transfers; sort them again.
    classify_ledger(store)
    return updated


def classify_ledger(store: Store) -> None:
    """Everything decided across rows rather than one row at a time, in the
    order the rules need: your exclusions first (they win, and an excluded row
    never pairs as a transfer), then transfer matching, then income types."""
    from .exclusions import reapply
    from .income import apply_income_types
    from .pay_rules import apply as apply_pay_rules
    reapply(store)
    # Her regular pay (2026-10-28) before transfers: a paycheque is never the
    # other end of one of her own transfers.
    apply_pay_rules(store)
    apply_transfer_matches(store)
    apply_income_types(store)
