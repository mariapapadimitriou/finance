"""Normalized transaction model shared by every ingestion source.

Sign convention (enforced at the boundary, relied on everywhere downstream):

    amount > 0   money left your pocket   (a purchase, a fee, interest)
    amount < 0   money came back          (a refund, a statement credit, a card payment)

Issuer exports disagree wildly about this -- Amex writes purchases positive,
Chase writes them negative, Capital One uses two separate columns. Each source
adapter is responsible for translating into the convention above so that
analytics never has to ask which bank a row came from.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date


# ── Merchant normalization ───────────────────────────────────────────────────
# Card descriptors are noisy: "SQ *BLUE BOTTLE COFFEE 4471 OAKLAND CA 09/14".
# We strip the noise down to a stable merchant key so the same coffee shop
# groups together across three different cards and two different processors.

_PROCESSOR_PREFIXES = [
    r"^SQ\s*\*",            # Square
    r"^TST\*\s*",           # Toast
    r"^SP\s+",              # Shopify / Shop Pay
    r"^PY\s*\*",            # Paysafe
    r"^PAYPAL\s*\*",
    r"^PP\s*\*",
    r"^IC\*\s*",            # Instacart
    r"^EIG\*\s*",
    r"^WPY\*\s*",           # WePay
    r"^CKO\*\s*",           # Checkout.com
    r"^POS\s+(?:PURCHASE\s+)?",
    r"^PURCHASE\s+(?:AUTHORIZED\s+ON\s+)?",
    r"^DEBIT\s+CARD\s+PURCHASE\s+",
    r"^VISA\s+DEBIT\s+",
    r"^INTERAC\s+(?:E-TRANSFER\s+)?",
    r"^AMZN\s+MKTP\b",      # collapse Amazon's many storefront descriptors
    r"^AMAZON\s+MKTPL?\b",
]

_NOISE_PATTERNS = [
    # Phone numbers first: they contain digit runs that the reference-number
    # rule below would otherwise chew in half, leaving "HULU 877- CA".
    r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",            # 866-579-7172
    r"\b\d{3}[-.\s]\d{7}\b",                       # 877-8244858
    r"\b\d{3}[-.][A-Z]{4,}\b",                     # 800-STATEFARM
    r"\b1[-.\s]?8\d{2}[-.\s]?[\w-]{7,}\b",         # 1-800-FLOWERS
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",           # embedded dates
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"#\s*\d+",                                    # store numbers
    r"\b\d{5,}\b",                                 # long reference numbers
    r"\bREF\s*\w+",
    r"\bAUTH\s*\w+",
    r"\bXX+\d+\b",
    r"\bCARD\s*\d+\b",
    r"\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b",
]

_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
    "US", "USA", "CAN",
}

# Domain and corporate suffixes that add nothing once the name is isolated.
_SUFFIX_NOISE = {"COM", "NET", "ORG", "CO", "INC", "LLC", "LTD", "CORP", "USA",
                 "STORE", "BILL", "PAYMENT"}

# Trailing "  CITY ST" / "  CITY, ON  CA" tails that vary by branch.
# The city is capped at two words on purpose: allowing unlimited words lets the
# pattern reach back and swallow part of the business name -- "ZEITGEIST BAR SAN
# FRANCISCO CA" would lose "BAR" along with the city, and with it the only clue
# that it's a bar. Three-word cities keep their first word, which is the far
# cheaper mistake.
_LOCATION_TAIL = re.compile(
    r"\s+[A-Z][A-Z\.\-']{0,17}(?:\s+[A-Z][A-Z\.\-']{0,17})?,?\s+"
    r"(?:A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|"
    r"N[EVHJMYCD]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[TA]|W[AVIY]|"
    r"AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)"
    r"(?:\s+(?:US|USA|CA|CAN))?\s*$"
)

_AMAZON_KEY = re.compile(r"\bAM(?:AZ)?ON\b|\bAMZN\b")


def normalize_merchant(description: str) -> str:
    """Reduce a raw card descriptor to a stable, human-readable merchant name."""
    if not description:
        return "Unknown"

    s = description.upper().strip()

    for pat in _PROCESSOR_PREFIXES:
        s = re.sub(pat, " ", s)

    s = _LOCATION_TAIL.sub("", s)

    for pat in _NOISE_PATTERNS:
        s = re.sub(pat, " ", s)

    # Collapse punctuation used as padding, but keep & and ' inside names.
    s = re.sub(r"[*_|]+", " ", s)
    s = re.sub(r"[^\w&'\-\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Amazon shows up a dozen ways; one key keeps its spend in one bucket.
    if _AMAZON_KEY.search(s):
        if "PRIME" in s and "VIDEO" not in s:
            return "Amazon Prime"
        if "WEB SERVICES" in s or s.startswith("AWS"):
            return "Amazon Web Services"
        return "Amazon"

    if not s:
        return "Unknown"

    # Trailing single letters / stray tokens left by stripping are noise.
    parts = [p for p in s.split() if not (len(p) == 1 and p.isalpha())]

    # Strip trailing state codes, domain suffixes and branch numbers, but never
    # eat the whole name -- "CO" alone is a merchant, "PEET'S CO" is not two
    # words worth keeping.
    while len(parts) > 1 and (
        parts[-1] in _STATES or parts[-1] in _SUFFIX_NOISE or parts[-1].isdigit()
    ):
        parts.pop()

    s = " ".join(parts) if parts else s

    return _titlecase(s)


_ALL_CAPS_KEEP = {
    "AMC", "AMEX", "ATM", "AT&T", "BP", "CVS", "DMV", "EA", "GM", "H&M",
    "HBO", "IGA", "IKEA", "KFC", "LCBO", "MTA", "NYC", "PG&E", "REI",
    "SFO", "TD", "TTC", "UPS", "USPS", "AWS", "IRS", "CRA", "SAQ", "GO",
}


def _titlecase(s: str) -> str:
    out = []
    for word in s.split():
        # Apostrophes and hyphens are part of names, not punctuation to trip on:
        # "JOE'S" and "PEET'S" must capitalize like any other word.
        letters = word.replace("'", "").replace("-", "")
        if word in _ALL_CAPS_KEEP or (len(word) <= 3 and not letters.isalpha()):
            out.append(word)
        elif letters.isalpha():
            out.append(word.capitalize())
        else:
            out.append(word)
    return " ".join(out)


# ── Transaction ──────────────────────────────────────────────────────────────

@dataclass
class Transaction:
    """One normalized line item.

    `fingerprint` and `seq` together form the identity used for cross-export
    deduplication -- see finance.dedupe for why the sequence number matters.
    """

    date: str                        # ISO YYYY-MM-DD, the transaction date
    description: str                 # raw descriptor, preserved verbatim
    amount: float                    # positive = outflow (see module docstring)
    account_id: str
    account_name: str = ""
    merchant: str = ""
    category: str = ""
    category_source: str = "rule"    # rule | user | merchant_override
    currency: str = "USD"
    post_date: str | None = None
    source: str = "csv"              # which adapter produced this row
    seq: int = 0                     # nth identical row within its own export
    raw: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.merchant:
            self.merchant = normalize_merchant(self.description)
        self.amount = round(float(self.amount), 2)

    @property
    def fingerprint(self) -> str:
        """Stable identity for a row, independent of which export it came from.

        Deliberately excludes post_date: the same purchase can post on
        different days in a mid-cycle export vs. a final statement, and we do
        not want that to look like two distinct charges.
        """
        key = "|".join([
            self.account_id,
            self.date,
            f"{self.amount:.2f}",
            re.sub(r"\s+", " ", self.description.upper().strip()),
            str(self.seq),
        ])
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]

    @property
    def is_spend(self) -> bool:
        return self.amount > 0

    @property
    def month(self) -> str:
        return self.date[:7]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.fingerprint
        d["raw"] = json.dumps(self.raw) if isinstance(self.raw, dict) else self.raw
        return d

    @classmethod
    def from_row(cls, row: dict) -> "Transaction":
        raw = row.get("raw") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raw = {}
        return cls(
            date=row["date"],
            description=row.get("description", ""),
            amount=row["amount"],
            account_id=row.get("account_id", ""),
            account_name=row.get("account_name", ""),
            merchant=row.get("merchant", ""),
            category=row.get("category", ""),
            category_source=row.get("category_source", "rule"),
            currency=row.get("currency", "USD"),
            post_date=row.get("post_date"),
            source=row.get("source", "csv"),
            seq=int(row.get("seq", 0) or 0),
            raw=raw,
        )


def parse_date(value: str) -> str | None:
    """Accept the date formats card issuers actually emit; return ISO or None."""
    if not value:
        return None
    v = value.strip()
    if not v:
        return None

    fmts = [
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y",
        "%Y/%m/%d", "%b %d, %Y", "%d-%b-%Y", "%d %b %Y", "%Y%m%d",
        "%m-%d-%Y", "%d.%m.%Y",
    ]
    from datetime import datetime
    for f in fmts:
        try:
            return datetime.strptime(v, f).date().isoformat()
        except ValueError:
            continue

    # ISO timestamps: keep the date half.
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ]", v)
    if m:
        return m.group(1)
    return None


def parse_amount(value) -> float | None:
    """Parse currency text into a float. Handles $, commas, and (parentheses)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[^\d\.,\-+]", "", s)
    if not s or s in {"-", "+", ".", ","}:
        return None

    # European style "1.234,56" -> comma is the decimal separator.
    if "," in s and "." in s:
        if s.rindex(",") > s.rindex("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.match(r"^-?\d{1,3}(,\d{3})+$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")

    try:
        amt = float(s)
    except ValueError:
        return None
    return -amt if negative else amt


def today() -> date:
    return date.today()
