"""CSV / statement-export ingestion.

Takes the file you downloaded from your card issuer, works out which issuer
wrote it, and returns normalized `Transaction` objects. No credentials, nothing
leaves the machine.
"""

from __future__ import annotations

import csv
import io
import re

from ..models import Transaction, parse_amount, parse_date
from . import schemas
from .base import IngestResult, SourceStatus, TransactionSource, register


class CsvSource(TransactionSource):
    key = "csv"
    label = "CSV / statement export"

    def status(self) -> SourceStatus:
        return SourceStatus(
            key=self.key,
            label=self.label,
            available=True,
            detail="Ready. Export a CSV from each card's website and upload it.",
            setup_steps=[
                "Sign in to your card issuer's site",
                "Find Statements & Activity → Download / Export",
                "Choose CSV and the widest date range offered",
                "Upload the file here — the format is detected automatically",
            ],
        )

    def fetch(self, files: list[dict] | None = None, **kwargs) -> list[IngestResult]:
        """`files` is a list of {name, content, account_name?, account_id?}."""
        results = []
        for f in files or []:
            results.append(parse_csv(
                content=f["content"],
                filename=f.get("name", "upload.csv"),
                account_name=f.get("account_name"),
                account_id=f.get("account_id"),
            ))
        return results


def _sniff_dialect(text: str) -> csv.Dialect | type[csv.Dialect]:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _read_rows(text: str) -> list[list[str]]:
    text = text.lstrip("﻿")
    dialect = _sniff_dialect(text)
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    return rows


def _preamble_offset(rows: list[list[str]]) -> int:
    """Some exports bury the real header under a few title/metadata lines."""
    for i, row in enumerate(rows[:8]):
        if schemas.looks_like_header_row(row):
            return i
        if parse_date(row[0] if row else "") is not None:
            return i
    return 0


def parse_csv(content: str, filename: str = "upload.csv",
              account_name: str | None = None,
              account_id: str | None = None) -> IngestResult:
    """Parse one CSV export into normalized transactions."""
    rows = _read_rows(content)
    if not rows:
        return IngestResult(transactions=[], format_key="unknown",
                            format_label="Empty file",
                            warnings=["File contained no rows."])

    start = _preamble_offset(rows)
    rows = rows[start:]
    first = rows[0]

    if schemas.looks_like_header_row(first):
        headers = [schemas.normalize_header(h) for h in first]
        data_rows = rows[1:]
        schema, confidence = schemas.detect(headers)
        cols = schemas.resolve_columns(schema, headers)
        records = [dict(zip(headers, r + [""] * (len(headers) - len(r)))) for r in data_rows]
        get = lambda rec, role: rec.get(cols.get(role, ""), "") if role in cols else ""
        desc_roles = cols.get("description", [])
    else:
        headers = []
        data_rows = rows
        schema, confidence = schemas.detect(None, sample_row=first)
        pos = schema.positional or {0: "date", 1: "description", 2: "amount"}
        records = []
        for r in data_rows:
            rec = {}
            for idx, role in pos.items():
                rec[role] = r[idx] if idx < len(r) else ""
            records.append(rec)
        get = lambda rec, role: rec.get(role, "")
        desc_roles = ["description"]

    acct_id, acct_name = _resolve_account(
        filename, schema, records, cols_card=(cols.get("card") if headers else None),
        account_name=account_name, account_id=account_id,
    )

    transactions: list[Transaction] = []
    skipped = 0
    warnings: list[str] = []

    for rec in records:
        iso = parse_date(str(get(rec, "date")))
        if iso is None:
            skipped += 1
            continue

        amount = _row_amount(rec, get, schema, headers)
        if amount is None:
            skipped += 1
            continue

        if headers and isinstance(desc_roles, list):
            parts = [str(rec.get(c, "")).strip() for c in desc_roles]
            description = " ".join(p for p in parts if p)
        else:
            description = str(get(rec, "description")).strip()
        if not description:
            description = "(no description)"

        post_iso = parse_date(str(get(rec, "post_date"))) if headers else None
        issuer_cat = str(get(rec, "category")).strip() if headers else ""

        transactions.append(Transaction(
            date=iso,
            post_date=post_iso,
            description=re.sub(r"\s+", " ", description),
            amount=amount,
            account_id=acct_id,
            account_name=acct_name,
            currency=schema.currency,
            source="csv",
            raw={"issuer_category": issuer_cat} if issuer_cat else {},
        ))

    _assign_sequence(transactions)

    if skipped:
        warnings.append(f"Skipped {skipped} row(s) with no readable date or amount.")
    if confidence < 0.5 and transactions:
        warnings.append(
            "Column layout was matched loosely — spot-check a few amounts and dates."
        )
    if transactions and all(t.amount <= 0 for t in transactions):
        warnings.append(
            "Every row parsed as an inflow. If these are purchases, the sign "
            "convention for this export may be inverted."
        )

    return IngestResult(
        transactions=transactions,
        account_id=acct_id,
        account_name=acct_name,
        format_key=schema.key,
        format_label=schema.label,
        confidence=confidence,
        skipped_rows=skipped,
        warnings=warnings,
    )


def _row_amount(rec, get, schema: schemas.CsvSchema, headers) -> float | None:
    """Resolve one row's amount into the positive-is-spending convention."""
    debit = parse_amount(get(rec, "debit")) if (schema.debit or not headers) else None
    credit = parse_amount(get(rec, "credit")) if (schema.credit or not headers) else None

    if debit or credit:
        # Debit columns are outflows, credit columns are inflows.
        return round(abs(debit or 0.0) - abs(credit or 0.0), 2)

    raw = parse_amount(get(rec, "amount"))
    if raw is None:
        return None
    return round(raw * schema.sign, 2)


_ACCT_CLEAN = re.compile(r"[^A-Za-z0-9]+")


def _resolve_account(filename, schema, records, cols_card,
                     account_name, account_id) -> tuple[str, str]:
    """Work out which card these rows belong to.

    An explicit name from the upload wins. Otherwise we look for a card-number
    column, then fall back to the filename, so two exports from the same card
    land in the same account across repeat imports.
    """
    if account_name:
        aid = account_id or _ACCT_CLEAN.sub("_", account_name).strip("_").lower()
        return aid, account_name

    last4 = ""
    if cols_card:
        for rec in records[:50]:
            val = str(rec.get(cols_card, "")).strip()
            digits = re.sub(r"\D", "", val)
            if len(digits) >= 4:
                last4 = digits[-4:]
                break

    stem = re.sub(r"\.csv$", "", filename, flags=re.I)
    stem = _ACCT_CLEAN.sub(" ", stem).strip()
    stem = " ".join(w.capitalize() if w.islower() else w for w in stem.split())

    if last4:
        name = f"{schema.label} ••{last4}"
        aid = f"{schema.key}_{last4}"
    elif stem:
        # "chase_sapphire.csv" from a Chase export should read "Chase Sapphire",
        # not "Chase — Chase Sapphire".
        issuer_word = schema.label.split()[0].lower()
        redundant = issuer_word in stem.lower() or schema.key == "generic"
        name = stem if redundant else f"{schema.label} — {stem}"
        aid = _ACCT_CLEAN.sub("_", f"{schema.key} {stem}").strip("_").lower()
    else:
        name = schema.label
        aid = schema.key

    return aid, name


def _assign_sequence(transactions: list[Transaction]) -> None:
    """Number identical rows within one export: 0, 1, 2...

    Two genuine $6.40 coffees on the same day are not duplicates of each other.
    Numbering them here means the fingerprint distinguishes them, while a
    re-import of the same file still collides exactly with the first import.
    """
    seen: dict[tuple, int] = {}
    for t in transactions:
        key = (t.account_id, t.date, f"{t.amount:.2f}",
               re.sub(r"\s+", " ", t.description.upper().strip()))
        t.seq = seen.get(key, 0)
        seen[key] = t.seq + 1


register(CsvSource())
