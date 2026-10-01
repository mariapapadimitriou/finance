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
        schema, confidence = schemas.detect(None, sample_rows=rows)
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

    def row_description(rec) -> str:
        if headers and isinstance(desc_roles, list):
            parts = [str(rec.get(c, "")).strip() for c in desc_roles]
            text = " ".join(p for p in parts if p)
        else:
            text = str(get(rec, "description")).strip()
        if not text:
            text = str(get(rec, "description_fallback")).strip() or "(no description)"
        return re.sub(r"\s+", " ", text)

    transactions: list[Transaction] = []
    skipped = 0
    warnings: list[str] = []

    # Which way round this file writes spending is a property of the file, not
    # of one row, so it is settled before any row is converted.
    sign, sign_warning = schema.sign, None
    if not (cols.get("debit") and cols.get("credit") if headers else False):
        raws = []
        for rec in records:
            raw = parse_amount(get(rec, "amount"))
            if raw is not None:
                raws.append((row_description(rec), raw))
        sign, sign_warning = infer_sign(raws, schema.sign)
    if sign_warning:
        warnings.append(sign_warning)

    for rec in records:
        iso = parse_date(str(get(rec, "date")))
        if iso is None:
            skipped += 1
            continue

        amount = _row_amount(rec, get, schema, headers, sign)
        if amount is None:
            skipped += 1
            continue

        description = row_description(rec)
        post_iso = parse_date(str(get(rec, "post_date"))) if headers else None
        issuer_cat = str(get(rec, "category")).strip() if headers else ""

        transactions.append(Transaction(
            date=iso,
            post_date=post_iso,
            description=description,
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
    inflows = sum(1 for t in transactions if t.amount <= 0)
    if transactions and inflows > len(transactions) * 0.8:
        warnings.append(
            f"{inflows} of {len(transactions)} rows parsed as money coming in. "
            "If these are purchases, the sign convention for this export is "
            "inverted — check a row you remember against the statement."
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


# A card payment is the one row on a credit-card export whose direction is never
# in doubt: it is money arriving to reduce the balance, never a purchase. That
# makes it a reference point for reading the rest of the file — whichever sign
# the issuer gave this row is the sign it uses for inflows, so spending is the
# other one.
#
# Kept deliberately narrow. "Pre-authorized payment" is an outflow on a
# chequing account and an inflow on a card, so it is left out; a hint that is
# sometimes backwards is worse than no hint.
_CARD_PAYMENT = re.compile(
    r"""(?xi)
      ^ payments? $                     # Wealthsimple writes it in a type column
    | \b payment \s* [-–—]* \s*
          (?: thank \s* you | from | received | web | online | cheque | check )
    | \b thank \s* you \s* [-–—]* \s* payment \b
    | \b pmt \s* thank \s* you \b
    | \b auto \s* -? \s* pay (?: ment )? \b
    """
)


def infer_sign(rows: list[tuple[str, float]], declared: int) -> tuple[int, str | None]:
    """Work out which direction this file calls spending.

    `rows` is (description, raw amount) as written in the file, before any sign
    is applied. Returns the sign to multiply by, and a warning when the file
    contradicts what the schema expected.

    The schema's sign is a prior: a note on what an issuer did when the layout
    was added. The file in front of us is evidence, and when the two disagree
    the file wins — issuers change their exports, and the same bank hands out
    different ones for cards and for chequing. Guessing wrong inverts every
    amount in the ledger, so the disagreement is reported rather than absorbed.
    """
    payments = [amt for desc, amt in rows if amt and _CARD_PAYMENT.search(desc or "")]
    if not payments:
        return declared, None

    # Contradictory evidence means this is not the clean signal we hoped for —
    # most likely a chequing export, where "payment" rows go both ways.
    if not (all(a > 0 for a in payments) or all(a < 0 for a in payments)):
        return declared, None

    # Inflows carry the payment rows' sign, so spending is the opposite.
    inferred = -1 if payments[0] > 0 else 1

    # Cross-check against the bulk of the file. On a card statement purchases
    # outnumber credits heavily, so if most other rows share the payments' sign
    # the reference point is not what we think it is.
    others = [amt for desc, amt in rows
              if amt and not _CARD_PAYMENT.search(desc or "")]
    if others:
        same_way = sum(1 for a in others if (a > 0) == (payments[0] > 0))
        if same_way > len(others) / 2:
            return declared, None

    if inferred == declared:
        return declared, None
    return inferred, (
        f"This export writes purchases as "
        f"{'positives' if inferred == 1 else 'negatives'}, which is the "
        f"opposite of what this issuer's layout usually does. The payment rows "
        f"were used to tell which way round it is, so spending is counted as "
        f"spending — but spot-check a few amounts."
    )


def _row_amount(rec, get, schema: schemas.CsvSchema, headers,
                sign: int | None = None) -> float | None:
    """Resolve one row's amount into the positive-is-spending convention."""
    debit = parse_amount(get(rec, "debit")) if (schema.debit or not headers) else None
    credit = parse_amount(get(rec, "credit")) if (schema.credit or not headers) else None

    if debit or credit:
        # Debit columns are outflows, credit columns are inflows.
        return round(abs(debit or 0.0) - abs(credit or 0.0), 2)

    raw = parse_amount(get(rec, "amount"))
    if raw is None:
        return None
    return round(raw * (schema.sign if sign is None else sign), 2)


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
    # Repeat downloads of one card arrive as "accountactivity (8).csv" or
    # "activities-2026-09-29.csv". The copy number and export date say nothing
    # about which card it is, and keeping them would file each download under
    # its own account, where overlapping rows are never de-duplicated.
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = re.sub(r"[-_ ]*\d{4}-\d{2}-\d{2}", "", stem)
    stem = _ACCT_CLEAN.sub(" ", stem).strip()
    stem = " ".join(w.capitalize() if w.islower() else w for w in stem.split())
    label = re.sub(r"\s*\(headerless\)$", "", schema.label)

    if last4:
        name = f"{label} ••{last4}"
        aid = f"{schema.key}_{last4}"
    elif stem:
        # "chase_sapphire.csv" from a Chase export should read "Chase Sapphire",
        # not "Chase — Chase Sapphire".
        issuer_word = label.split()[0].lower()
        redundant = issuer_word in stem.lower() or schema.key == "generic"
        name = stem if redundant else f"{label} — {stem}"
        aid = _ACCT_CLEAN.sub("_", f"{schema.key} {stem}").strip("_").lower()
    else:
        name = label
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
