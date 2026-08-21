"""Column layouts for the CSV exports real card issuers hand you.

Each issuer names its columns differently and disagrees about which direction is
"spending", so a schema records both the column mapping and the sign convention.
`detect()` scores a file's headers against every schema and picks the best match;
`GENERIC` catches anything unrecognized by matching on keywords instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class CsvSchema:
    key: str
    label: str
    # Header tokens that identify this issuer. Detection is scored against these.
    signature: list[str] = field(default_factory=list)
    date: list[str] = field(default_factory=list)
    post_date: list[str] = field(default_factory=list)
    description: list[str] = field(default_factory=list)
    amount: list[str] = field(default_factory=list)
    debit: list[str] = field(default_factory=list)
    credit: list[str] = field(default_factory=list)
    category: list[str] = field(default_factory=list)
    card: list[str] = field(default_factory=list)
    # +1: the amount column is already positive-for-spending.
    # -1: the issuer writes purchases as negatives; flip them.
    sign: int = 1
    currency: str = "USD"
    # Headerless exports (several Canadian banks, Wells Fargo) are matched by
    # column position instead. Index -> field name.
    positional: dict[int, str] | None = None
    columns: int = 0


SCHEMAS: list[CsvSchema] = [
    CsvSchema(
        key="amex",
        label="American Express",
        signature=["date", "description", "amount", "card member"],
        date=["date"],
        description=["description", "extended details"],
        amount=["amount"],
        category=["category"],
        card=["account #", "card member"],
        sign=1,  # Amex writes charges positive
    ),
    CsvSchema(
        key="chase",
        label="Chase",
        signature=["transaction date", "post date", "description", "category", "type", "amount"],
        date=["transaction date"],
        post_date=["post date", "posting date"],
        description=["description"],
        amount=["amount"],
        category=["category"],
        sign=-1,  # Chase writes purchases negative
    ),
    CsvSchema(
        key="capital_one",
        label="Capital One",
        signature=["transaction date", "posted date", "card no.", "description", "debit", "credit"],
        date=["transaction date"],
        post_date=["posted date"],
        description=["description"],
        debit=["debit"],
        credit=["credit"],
        category=["category"],
        card=["card no.", "card no"],
    ),
    CsvSchema(
        key="citi",
        label="Citi",
        signature=["status", "date", "description", "debit", "credit"],
        date=["date"],
        description=["description"],
        debit=["debit"],
        credit=["credit"],
    ),
    CsvSchema(
        key="discover",
        label="Discover",
        signature=["trans. date", "post date", "description", "amount", "category"],
        date=["trans. date", "trans date"],
        post_date=["post date"],
        description=["description"],
        amount=["amount"],
        category=["category"],
        sign=1,
    ),
    CsvSchema(
        key="bofa",
        label="Bank of America",
        signature=["posted date", "reference number", "payee", "address", "amount"],
        date=["posted date"],
        description=["payee"],
        amount=["amount"],
        sign=-1,
    ),
    CsvSchema(
        key="rbc",
        label="RBC Royal Bank",
        signature=["account type", "account number", "transaction date", "description 1", "cad$"],
        date=["transaction date"],
        description=["description 1", "description 2"],
        amount=["cad$", "cad", "amount"],
        card=["account number"],
        sign=-1,  # RBC writes purchases negative
        currency="CAD",
    ),
    CsvSchema(
        key="scotiabank",
        label="Scotiabank",
        signature=["date", "amount", "description"],
        date=["date"],
        description=["description"],
        amount=["amount"],
        sign=-1,
        currency="CAD",
    ),
    CsvSchema(
        key="wells_fargo",
        label="Wells Fargo (headerless)",
        positional={0: "date", 1: "amount", 4: "description"},
        columns=5,
        sign=-1,
        currency="USD",
    ),
    CsvSchema(
        key="td_canada",
        label="TD Canada (headerless)",
        positional={0: "date", 1: "description", 2: "debit", 3: "credit"},
        columns=5,
        currency="CAD",
    ),
]

# Last resort: match by keyword rather than by exact issuer layout.
GENERIC = CsvSchema(
    key="generic",
    label="Generic CSV",
    date=["transaction date", "trans date", "trans. date", "date", "posted date",
          "post date", "purchase date", "activity date"],
    post_date=["posted date", "post date", "posting date", "settlement date"],
    description=["description", "payee", "merchant", "name", "details",
                 "transaction", "memo", "narrative", "description 1"],
    amount=["amount", "transaction amount", "value", "cad$", "usd$", "amt"],
    debit=["debit", "withdrawal", "withdrawals", "money out", "charge"],
    credit=["credit", "deposit", "deposits", "money in", "payment"],
    category=["category", "type", "classification"],
    card=["card no.", "card no", "account number", "account #", "account"],
    sign=1,
)

_HEADER_TOKENS = {
    "date", "description", "amount", "debit", "credit", "payee", "category",
    "merchant", "transaction", "post", "posted", "balance", "type", "status",
    "reference", "account", "card", "memo", "details", "trans",
}


def normalize_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower().lstrip("﻿"))


def looks_like_header_row(cells: list[str]) -> bool:
    """True when the first CSV row names columns rather than holding data."""
    if not cells:
        return False
    joined = " ".join(normalize_header(c) for c in cells)
    hits = sum(1 for tok in _HEADER_TOKENS if tok in joined)
    # A data row's first cell is a date; a header row's first cell is a word.
    from ..models import parse_date
    first_is_date = parse_date(cells[0]) is not None
    return hits >= 2 and not first_is_date


def score_schema(schema: CsvSchema, headers: list[str]) -> float:
    """How well a schema's signature matches this file's headers (0.0 - 1.0)."""
    if not schema.signature:
        return 0.0
    hset = set(headers)
    hits = sum(1 for token in schema.signature if token in hset)
    coverage = hits / len(schema.signature)
    # Penalize partial matches that would also match a rival issuer.
    return coverage if hits >= 2 else coverage * 0.5


def detect(headers: list[str] | None, sample_row: list[str] | None = None
           ) -> tuple[CsvSchema, float]:
    """Pick the best schema for a file. Returns (schema, confidence)."""
    if headers:
        norm = [normalize_header(h) for h in headers]
        best, best_score = GENERIC, 0.0
        for schema in SCHEMAS:
            if schema.positional:
                continue
            s = score_schema(schema, norm)
            if s > best_score:
                best, best_score = schema, s
        if best_score >= 0.6:
            return best, best_score
        # Generic still works as long as we can find a date and an amount.
        return GENERIC, _generic_confidence(norm)

    # Headerless: match on column count and the shape of the first data row.
    if sample_row:
        n = len(sample_row)
        for schema in SCHEMAS:
            if schema.positional and schema.columns == n:
                return schema, 0.55
    return GENERIC, 0.0


def _generic_confidence(headers: list[str]) -> float:
    has_date = any(_find(headers, GENERIC.date))
    has_desc = any(_find(headers, GENERIC.description))
    has_amt = any(_find(headers, GENERIC.amount + GENERIC.debit + GENERIC.credit))
    return round(0.34 * sum([bool(has_date), bool(has_desc), bool(has_amt)]), 2)


def _find(headers: list[str], candidates: list[str]) -> list[str]:
    """Return the headers matching any candidate, most-specific first."""
    out = []
    for cand in candidates:
        for h in headers:
            if h == cand and h not in out:
                out.append(h)
    for cand in candidates:
        for h in headers:
            if cand in h and h not in out:
                out.append(h)
    return out


def resolve_columns(schema: CsvSchema, headers: list[str]) -> dict[str, str | list[str]]:
    """Map schema roles onto this file's actual header names."""
    norm = [normalize_header(h) for h in headers]
    cols: dict[str, str | list[str]] = {}

    def pick(role: str, fallback: list[str]) -> None:
        candidates = getattr(schema, role) or fallback
        found = _find(norm, candidates)
        if found:
            cols[role] = found[0]

    pick("date", GENERIC.date)
    pick("post_date", GENERIC.post_date)
    pick("amount", GENERIC.amount)
    pick("debit", GENERIC.debit)
    pick("credit", GENERIC.credit)
    pick("category", GENERIC.category)
    pick("card", GENERIC.card)

    # Description can span several columns (RBC splits it across two).
    desc_cands = schema.description or GENERIC.description
    desc_cols = _find(norm, desc_cands)
    if desc_cols:
        cols["description"] = desc_cols[:2]

    # A debit/credit pair beats a signed amount column when both exist.
    if "debit" in cols and "credit" in cols:
        cols.pop("amount", None)

    return cols
