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
    r"^TST[\*\-]\s*",       # Toast — both the TST* and TST- spellings
    r"^SP\s+",              # Shopify / Shop Pay
    r"^PY\s*\*",            # Paysafe
    r"^PAYPAL\s*\*",
    r"^PP\s*\*",
    r"^IC\*\s*",            # Instacart
    r"^EIG\*\s*",
    r"^WPY\*\s*",           # WePay
    r"^CKO\*\s*",           # Checkout.com
    r"^EB\s*\*",            # Eventbrite
    r"^POS\s+(?:PURCHASE\s+)?",
    r"^PURCHASE\s+(?:AUTHORIZED\s+ON\s+)?",
    r"^DEBIT\s+CARD\s+PURCHASE\s+",
    r"^VISA\s+DEBIT\s+",
    r"^INTERAC\s+(?:E-TRANSFER\s+)?",
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

# A wallet tag sits *after* the city and province, so it has to come off before
# the location tail is looked for — otherwise "TORONTO ON" is no longer at the
# end of the string and every tap-to-pay row keeps its city in the merchant
# name. Scotiabank appends it to almost every row.
_WALLET_TAIL = re.compile(
    r"\s*\(?\b(?:APPLE|GOOGLE|SAMSUNG|GARMIN|FITBIT)\s*-?\s*PAY\b\)?\s*$"
)

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

# Words that start a two-word city and are never the last word of a merchant
# name. Only with one of these trailing does the two-word city reading win.
_CITY_LEAD = {
    "SAN", "SANTA", "SANTO", "LOS", "LAS", "NEW", "NORTH", "SOUTH", "EAST",
    "WEST", "PORT", "SAINT", "ST", "FORT", "FT", "LAKE", "MOUNT", "MT",
    "GRAND", "SALT", "DES", "EL", "THOUSAND", "NIAGARA", "THUNDER", "SAULT",
    "OKLAHOMA", "KANSAS", "SIOUX", "BATON", "LITTLE", "CORAL", "PALM", "BOCA",
    "CEDAR", "RICHMOND", "COLORADO", "SURREY", "OWEN", "SWIFT", "MEDICINE",
    "PRINCE", "RED", "MOOSE", "CHESTNUT", "BAY", "WHITE", "LONG", "HIGH",
}

_AMAZON_KEY = re.compile(r"\bAM(?:AZ)?ON\b|\bAMZN\b")


def normalize_merchant(description: str) -> str:
    """Reduce a raw card descriptor to a stable, human-readable merchant name."""
    if not description:
        return "Unknown"

    s = description.upper().strip()

    # Amazon first, against the descriptor as written.
    #
    # It used to be collapsed by stripping "AMZN MKTP" as though it were a
    # processor prefix, which removed the only word identifying Amazon —
    # leaving "AMZN MKTP CA" as the country code alone, a merchant called
    # "Ca". The key below is the thing that recognises Amazon, so it has to
    # see the descriptor before anything is taken off it.
    if _AMAZON_KEY.search(s):
        if "PRIME" in s and "VIDEO" not in s:
            return "Amazon Prime"
        if "WEB SERVICES" in s or "AWS" in s.split():
            return "Amazon Web Services"
        return "Amazon"

    for pat in _PROCESSOR_PREFIXES:
        s = re.sub(pat, " ", s)

    s = _WALLET_TAIL.sub("", s).strip() or s
    s = _strip_location_tail(s)

    for pat in _NOISE_PATTERNS:
        s = re.sub(pat, " ", s)

    # Collapse punctuation used as padding, but keep & and ' inside names.
    s = re.sub(r"[*_|]+", " ", s)
    s = re.sub(r"[^\w&'\-\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

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


# Same tail, but a single-word city — the fallback when the two-word form
# would consume the merchant name entirely.
_LOCATION_TAIL_SHORT = re.compile(
    r"\s+[A-Z][A-Z\.\-']{0,17},?\s+"
    r"(?:A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|"
    r"N[EVHJMYCD]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[TA]|W[AVIY]|"
    r"AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)"
    r"(?:\s+(?:US|USA|CA|CAN))?\s*$"
)

_ALL_CAPS_KEEP = {"AMC", "AMEX", "ATM", "AT&T", "BP", "CVS", "DMV", "EA", "GM", "H&M",
    "HBO", "IGA", "IKEA", "KFC", "LCBO", "MTA", "NYC", "PG&E", "REI",
    "SFO", "TD", "TTC", "UPS", "USPS", "AWS", "IRS", "CRA", "SAQ", "GO",
}


def _strip_location_tail(s: str) -> str:
    """Remove a trailing "CITY ST" without swallowing the merchant name.

    The city may be two words ("SAN FRANCISCO", "NEW YORK"), but a two-word
    match cannot tell a two-word city from a one-word city preceded by the last
    word of the name: "QUEEN'S CROSS FOOD HALL TORONTO ON" fits the pattern
    just as well as "UBER TRIP SAN FRANCISCO CA", and reading it that way
    leaves "Queen's Cross Food".

    So the one-word city is tried first and kept unless what it leaves behind
    ends in a word that only ever begins a city name. Those words are listed
    rather than guessed, because the alternative is a rule that quietly trims a
    word off a merchant.
    """
    short = _LOCATION_TAIL_SHORT.sub("", s).strip()
    if short:
        if short.split()[-1].rstrip(".") in _CITY_LEAD:
            longer = _LOCATION_TAIL.sub("", s).strip()
            if longer:
                return longer
        return short

    # The one-word form consumed everything, so the name itself must be inside
    # what looked like the city.
    return _LOCATION_TAIL.sub("", s).strip() or s


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
    # Set when this charge has been assigned to a piggy bank, which takes it
    # out of the month it fell in — see finance/piggy.py. Deliberately not part
    # of the fingerprint: allocating a charge does not make it a different
    # charge, and a re-import must not create a second copy of it.
    bank_id: int | None = None
    # How much of this charge the bank paid. Not always the whole of it: a bank
    # holding $400 covers $400 of a $2,000 flight and the other $1,600 stays in
    # the month it was spent.
    bank_amount: float = 0.0
    # True when the bank pays for it because the bank owns its category,
    # rather than because someone allocated this charge by hand.
    bank_auto: bool = False
    # How much of the charge was yours, when friends paid you back for the
    # rest. None means all of it. Not part of the fingerprint, for the same
    # reason the bank is not.
    my_share: float | None = None
    # How much of it was put away (saved), when only part was. None means
    # none of it; a whole transfer is categorised Saved instead.
    invested: float | None = None
    # On a charge: what friends have sent back for it, linked by you. Your
    # share is what is left, unless you typed one yourself.
    paid_back: float | None = None
    # On money coming in: the charge it paid you back for.
    repays: str | None = None
    # The label of the joint account this row is on ("Family"), if it is one.
    # On a joint account a row is another member's unless you said otherwise,
    # so its share defaults to nothing — `share_set` says whether you did.
    joint: str | None = None
    share_set: bool = False

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
        t = cls(
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
            bank_id=row.get("bank_id"),
            bank_amount=float(row.get("bank_amount") or 0.0),
            bank_auto=bool(row.get("bank_auto") or 0),
            my_share=(None if row.get("my_share") is None
                      else float(row["my_share"])),
            invested=(None if row.get("invested") is None
                      else float(row["invested"])),
            paid_back=(None if row.get("paid_back") is None
                       else round(float(row["paid_back"]), 2)),
            repays=row.get("repays"),
            joint=row.get("joint") or None,
            share_set=row.get("my_share") is not None,
        )
        if t.joint and t.my_share is None:
            # Another member's, unless it's a name you said is always yours.
            t.my_share = t.amount if row.get("joint_mine") else 0.0
        return t


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
