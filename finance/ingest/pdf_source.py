"""PDF statement ingestion.

Some issuers only hand you PDFs. This reads them directly rather than making
you retype anything, using the same `TransactionSource` contract as the CSV
importer — so dedupe, categorization, analytics and insights treat a PDF
statement exactly like a CSV export.

Currently implements the Scotiabank Amex statement layout:

    REF.#  TRANS.DATE  POST.DATE  DETAILS                      AMOUNT($)
    001    Feb 19      Feb 21     RABBA #155 Q4 TORONTO ON         18.03
           (APPLE PAY)
    020    Feb 28      Feb 28     PAYMENT FROM - *****10*6822     942.91-

Two details drive the design. Transaction dates carry no year, so the year is
inferred from the statement period, which is the only place it appears. And a
trailing minus marks a credit — a payment or refund — which becomes a negative
amount under the positive-is-spending convention.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from ..models import Transaction
from .base import IngestResult, SourceStatus, TransactionSource, register

# 001    Feb 19   Feb 21   DETAILS...   18.03[-]
TXN_LINE = re.compile(
    r"^(?P<ref>\d{3})\s+"
    r"(?P<trans>[A-Z][a-z]{2}\s+\d{1,2})\s+"
    r"(?P<post>[A-Z][a-z]{2}\s+\d{1,2})\s+"
    r"(?P<details>.+?)\s+"
    r"(?P<amount>[\d,]+\.\d{2})(?P<credit>-?)$"
)

PERIOD = re.compile(
    r"StatementPeriod\s*(?P<start>[A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})\s*-\s*"
    r"(?P<end>[A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})"
)

ACCOUNT = re.compile(r"Account#\s*(?P<num>[\dX]+(?:\s+[\dX]+)*)")

# Wallet markers sit on their own line under the transaction they belong to.
# They say how it was paid, not what was bought, so they add nothing.
CONTINUATION = re.compile(r"^\((?:APPLE PAY|GOOGLE PAY|SAMSUNG PAY)\)$", re.I)

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def _parse_period_date(text: str) -> date | None:
    m = re.match(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})", text.strip())
    if not m:
        return None
    month = MONTHS.get(m.group(1))
    if not month:
        return None
    return date(int(m.group(3)), month, int(m.group(2)))


def _resolve_year(month_day: str, period_start: date, period_end: date) -> date | None:
    """Give a bare "Feb 19" the year implied by the statement period.

    A statement spanning a year boundary (Dec 21 - Jan 20) contains both years,
    so every plausible year is tried and the one landing nearest the period
    wins. Transaction dates legitimately precede the period start by a few days,
    since a charge posts after it is made.
    """
    m = re.match(r"([A-Z][a-z]{2})\s+(\d{1,2})$", month_day.strip())
    if not m:
        return None
    month = MONTHS.get(m.group(1))
    if not month:
        return None
    day = int(m.group(2))

    best, best_distance = None, None
    for year in {period_start.year, period_end.year, period_start.year - 1}:
        try:
            candidate = date(year, month, day)
        except ValueError:      # Feb 29 in a non-leap year
            continue
        if candidate < period_start - timedelta(days=60):
            continue
        if candidate > period_end + timedelta(days=10):
            continue
        # Distance from the period, zero while inside it.
        distance = max(
            (period_start - candidate).days, (candidate - period_end).days, 0
        )
        if best_distance is None or distance < best_distance:
            best, best_distance = candidate, distance
    return best


def extract_text(data: bytes | str) -> str:
    """Pull the text layer out of a PDF. Accepts raw bytes or a file path."""
    import io

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "Reading PDF statements needs pdfplumber. Run: pip install pdfplumber"
        ) from exc

    source = io.BytesIO(data) if isinstance(data, bytes) else data
    with pdfplumber.open(source) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def parse_statement(data: bytes | str, filename: str = "statement.pdf",
                    account_name: str | None = None) -> IngestResult:
    """Parse one PDF statement into normalized transactions."""
    try:
        text = extract_text(data)
    except RuntimeError as exc:
        return IngestResult(transactions=[], format_key="pdf",
                            format_label="PDF statement", warnings=[str(exc)])

    warnings: list[str] = []

    period = PERIOD.search(text)
    if not period:
        return IngestResult(
            transactions=[], format_key="pdf", format_label="PDF statement",
            warnings=["Could not find a statement period, so transaction dates "
                      "have no year to attach to. Is this a Scotiabank statement?"],
        )

    start = _parse_period_date(period.group("start"))
    end = _parse_period_date(period.group("end"))
    if not start or not end:
        return IngestResult(transactions=[], format_key="pdf",
                            format_label="PDF statement",
                            warnings=["Statement period was unreadable."])

    acct_id, acct_label = _resolve_account(text, account_name)

    transactions: list[Transaction] = []
    skipped = 0

    for raw in text.splitlines():
        line = raw.strip()
        if not line or CONTINUATION.match(line):
            continue

        m = TXN_LINE.match(line)
        if not m:
            continue

        when = _resolve_year(m.group("trans"), start, end)
        posted = _resolve_year(m.group("post"), start, end)
        if when is None:
            skipped += 1
            continue

        amount = float(m.group("amount").replace(",", ""))
        # A trailing minus marks a credit: a payment, a refund, points redeemed.
        if m.group("credit"):
            amount = -amount

        transactions.append(Transaction(
            date=when.isoformat(),
            post_date=posted.isoformat() if posted else None,
            description=_clean_details(m.group("details")),
            amount=amount,
            account_id=acct_id,
            account_name=acct_label,
            currency="CAD",
            source="pdf",
            raw={"ref": m.group("ref"), "statement": filename},
        ))

    _assign_sequence(transactions)

    if skipped:
        warnings.append(f"Skipped {skipped} line(s) whose date could not be resolved.")
    if not transactions:
        warnings.append("No transactions found. The PDF may be a scan with no "
                        "text layer, which this importer cannot read.")

    return IngestResult(
        transactions=transactions,
        account_id=acct_id,
        account_name=acct_label,
        format_key="scotiabank_pdf",
        format_label="Scotiabank statement (PDF)",
        confidence=0.95 if transactions else 0.0,
        skipped_rows=skipped,
        warnings=warnings,
    )


# The city/province tail often runs straight into the merchant name because the
# PDF's columns collide: "IQ FOOD CO. FCP 213133251TORONTO ON".
_GLUED_CITY = re.compile(r"(?<=[a-z0-9])(?=[A-Z]{3,}\s+(?:ON|QC|BC|AB|NY|CA)\b)")


def _clean_details(details: str) -> str:
    text = re.sub(r"\s+", " ", details).strip()
    return _GLUED_CITY.sub(" ", text)


def _resolve_account(text: str, account_name: str | None) -> tuple[str, str]:
    m = ACCOUNT.search(text)
    digits = ""
    if m:
        tail = m.group("num").split()[-1]
        digits = re.sub(r"\D", "", tail)

    if account_name:
        key = re.sub(r"[^A-Za-z0-9]+", "_", account_name).strip("_").lower()
        return key, account_name

    if digits:
        return f"scotiabank_{digits}", f"Scotiabank Gold Amex ••{digits[-4:]}"
    return "scotiabank", "Scotiabank Gold Amex"


def _assign_sequence(transactions: list[Transaction]) -> None:
    """Number identical rows so genuine repeat purchases survive dedupe."""
    seen: dict[tuple, int] = {}
    for t in transactions:
        key = (t.account_id, t.date, f"{t.amount:.2f}",
               re.sub(r"\s+", " ", t.description.upper().strip()))
        t.seq = seen.get(key, 0)
        seen[key] = t.seq + 1


class PdfSource(TransactionSource):
    key = "pdf"
    label = "PDF statement"

    def status(self) -> SourceStatus:
        try:
            import pdfplumber  # noqa: F401
            ready = True
        except ImportError:
            ready = False

        return SourceStatus(
            key=self.key,
            label=self.label,
            available=ready,
            detail=("Ready. Upload the PDF statements you download from your bank."
                    if ready else
                    "Needs pdfplumber — run: pip install pdfplumber"),
            setup_steps=[
                "Sign in to your bank and open Statements",
                "Download the monthly PDF statements you want to analyze",
                "Upload them here — dates, amounts and merchants are read directly",
                "Text-based statements only; a scanned image needs OCR first",
            ],
        )

    def fetch(self, files: list[dict] | None = None, **kwargs) -> list[IngestResult]:
        return [
            parse_statement(f["content"], f.get("name", "statement.pdf"),
                            f.get("account_name"))
            for f in (files or [])
        ]


register(PdfSource())
