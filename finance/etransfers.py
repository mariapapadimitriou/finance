"""Who an Interac e-Transfer was from, or to.

Banks write e-Transfers as "E-TRANSFER RECEIVED PRIYA SHAH", "INTERAC
E-TRF FROM SAM", "SEND E-TFR ***Q7k" — the person, when there is one, is
buried in the bank's wording. The list shows the person instead (THL-122).
In order: the name she typed for this one, the counterparty the bank feed
named, and the words left once the bank's own are taken out. With none, the
transaction detail asks "Who sent this?".
"""

from __future__ import annotations

import re

from .models import Transaction

_ETRANSFER = re.compile(r"\b(e-?\s?transfers?|e-?\s?tfr|etfr|e-?trf|interac|autodeposit)\b", re.I)

# The bank's words, never part of a name.
_BANK_WORDS = {
    "interac", "e", "transfer", "transfers", "etransfer", "etransfers", "tfr", "etfr", "trf",
    "autodeposit", "auto", "deposit", "deposited", "received", "recv", "rcvd", "sent", "send",
    "from", "to", "money", "request", "requested", "fulfilled", "fulfill", "cancelled",
    "canceled", "reclaim", "reclaimed", "payment", "pmt", "fee", "service", "charge", "online",
    "mobile", "banking", "bank", "web", "www", "ref", "reference", "conf", "confirmation", "no",
    "number", "msg", "memo", "for", "via", "the", "of", "and", "a", "ca", "cad", "ach", "credit",
    "debit", "inc", "ltd",
    # Wealthsimple Pay's own words: "Cash Received - anastasiapapas".
    "cash", "pay",
    # Banks, which a feed sometimes names as the counterparty.
    "td", "rbc", "bmo", "cibc", "scotiabank", "scotia", "tangerine", "simplii", "eq",
    "desjardins", "hsbc", "national", "wealthsimple", "koho", "neo", "atb", "pc", "financial",
}


# Wealthsimple Pay (2026-10-28): money sent between Wealthsimple accounts by
# handle. The bank writes "Cash Received - anastasiapapas" or "Cash Sent -
# anastasiapapas": a person's handle, their first and last name run
# together, not a cash deposit and not her own money moving.
_WS_PAY = re.compile(r"^\s*cash\s+(?:received|sent)\s*[-–—:]\s*\$?([A-Za-z0-9._']{2,40})\s*$", re.I)
_WS_PAY_WORDS = re.compile(r"\b(?:wealthsimple|ws)\s+pay\b", re.I)


def handle(t: Transaction) -> str | None:
    """The Wealthsimple Pay handle a row names ("anastasiapapas"), or None."""
    raw = t.raw or {}
    for text in (t.description, raw.get("plaid_name"), raw.get("original_description"), t.merchant):
        m = _WS_PAY.match(str(text or ""))
        if m:
            return m.group(1)
    return None


def is_etransfer(t: Transaction) -> bool:
    """Money sent to or from a person: an Interac e-Transfer, or Wealthsimple
    Pay (2026-10-28)."""
    raw = t.raw or {}
    text = " ".join(str(x or "") for x in (
        t.description, t.merchant, raw.get("counterparty"), raw.get("plaid_name"),
        raw.get("original_description")))
    return bool(_ETRANSFER.search(text) or _WS_PAY_WORDS.search(text) or handle(t))


def person_for(tag: str, people) -> str | None:
    """The one person she named whose first name a handle starts with:
    "anastasiapapas" is the Anastasia of her splits or her joint account.
    Three letters at least, and only when it's one person: "al" could be
    anyone, and so could a handle two of her people's names fit."""
    tag = re.sub(r"[^a-zà-ÿ]", "", (tag or "").lower())
    hits = {}
    for name in people or []:
        words = re.findall(r"[a-zà-ÿ']+", (name or "").lower())
        first = words[0] if words else ""
        if len(first) >= 3 and tag.startswith(first):
            hits.setdefault(first, name)
    return next(iter(hits.values())) if len(hits) == 1 else None


def handle_matches(t: Transaction, first: str) -> bool:
    """Whether a Wealthsimple Pay handle starts with this first name."""
    tag = handle(t)
    first = (first or "").lower()
    return bool(tag) and len(first) >= 3 and re.sub(r"[^a-zà-ÿ]", "", tag.lower()).startswith(first)


def _name_in(text: str) -> str | None:
    """The person in a bank's description, or None."""
    words = []
    for w in re.split(r"[\s*#:/,.()\-]+", text or ""):
        if not w or any(ch.isdigit() for ch in w):
            continue                       # reference codes: ***Q7k1, CA1234
        if w.lower() in _BANK_WORDS or not re.fullmatch(r"[A-Za-zÀ-ÿ']+", w):
            continue
        words.append(w)
    if not 1 <= len(words) <= 4 or all(len(w) < 2 for w in words):
        return None
    return " ".join(w if any(c.islower() for c in w) else w.capitalize() for w in words)


def known_people(transactions, splits: dict | None = None, payer: dict | None = None) -> list[str]:
    """The names she uses for people: in her splits, on her joint accounts,
    and who she said paid her back."""
    names: list[str] = []
    for sp in (splits or {}).values():
        names += [p.get("name") or "" for p in sp.get("people") or []]
    for t in transactions:
        names += list(getattr(t, "joint_people", None) or [])
    names += list((payer or {}).values())
    seen, out = set(), []
    for n in names:
        n = " ".join(str(n or "").split())
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def party(t: Transaction, people=None) -> dict | None:
    """{"direction": "from" | "to", "name": str | None, "named_by": "you" |
    "bank" | None} for an e-Transfer; None for anything else.

    `people` are the names she uses (her splits, her joint accounts, who
    paid her back): a Wealthsimple Pay handle reads as the one of them it
    starts with, "Anastasia" rather than "Anastasiapapas"."""
    if not is_etransfer(t) and not t.party:
        return None
    direction = "from" if t.amount < 0 else "to"
    if t.party:
        return {"direction": direction, "name": t.party, "named_by": "you"}
    tag = handle(t)
    if tag:
        known = person_for(tag, people)
        return {"direction": direction, "handle": tag,
                "name": known or (tag[:1].upper() + tag[1:] if tag.islower() else tag),
                "named_by": "bank"}
    raw = t.raw or {}
    # Plaid's payment_meta names the payer of money in and the payee of
    # money out, when the bank sends it (2026-10-22); then the counterparty,
    # then the bank's wording.
    named = str(raw.get("payer" if direction == "from" else "payee") or "").strip()
    counterparty = str(raw.get("counterparty") or "").strip()
    name = (_name_in(named) if named else None) \
        or (_name_in(counterparty) if counterparty and not _ETRANSFER.fullmatch(counterparty)
            else None) \
        or _name_in(t.description)
    return {"direction": direction, "name": name, "named_by": "bank" if name else None}



# ── The sender's message (2026-10-21) ─────────────────────────────────────

# What a bank writes before an e-Transfer's message, when it labels it.
_MEMO_MARK = re.compile(r"(?:\bmemo|\bmsg|\bmessage|\bnote|\bcomment)s?\s*[:\-=]\s*(.+)$", re.I)


def memo(t: Transaction) -> str | None:
    """The message a friend wrote on an e-Transfer ("uber eats", "for rent"),
    when the bank passed it on, else None.

    From the bank's original description: what follows "MEMO:" or "MSG:"
    when a bank labels it, otherwise whatever is left once the bank's own
    words, reference codes and the person's name are taken out.
    """
    if not is_etransfer(t):
        return None
    raw = t.raw or {}
    # Plaid's payment_meta.reason is "the payer-supplied description" itself.
    reason = " ".join(str(raw.get("reason") or "").split())
    if reason:
        return reason[:80]
    text = str(raw.get("original_description") or "").strip()
    if not text:
        return None
    m = _MEMO_MARK.search(text)
    if m:
        out = " ".join(m.group(1).split()).strip(" .;:-")
        return out[:80] or None
    who = party(t) or {}
    name_words = {w.lower() for w in re.split(r"\s+", who.get("name") or "") if w}
    for extra in (t.description, t.merchant, raw.get("counterparty")):
        for w in re.split(r"[\s*#:/,.()\-]+", str(extra or "")):
            if w and w.lower() not in _BANK_WORDS:
                name_words.add(w.lower())
    words = []
    for w in re.split(r"[\s*#:/,.()\-]+", text):
        if not w or any(ch.isdigit() for ch in w):
            continue
        lw = w.lower()
        if lw in _BANK_WORDS or lw in name_words or not re.fullmatch(r"[A-Za-zÀ-ÿ'&]+", w):
            continue
        words.append(w)
    if not words or all(len(w) < 3 for w in words):
        return None
    return " ".join(w.lower() if w.isupper() else w for w in words)[:80]


_STOP = {"the", "for", "and", "my", "your", "our", "dinner", "lunch", "share", "thanks", "thank",
         "you", "half", "split", "back", "owe", "owed", "last", "night", "today", "yesterday"}


def memo_words(text: str | None) -> set[str]:
    """The words in a message worth matching against a merchant's name."""
    return {w for w in re.split(r"[^a-zà-ÿ0-9&']+", (text or "").lower())
            if len(w) >= 3 and w not in _STOP}
