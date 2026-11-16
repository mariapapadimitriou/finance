"""Short account names: the one place they are made (Your accounts v2,
AS-01 v2 1415:87857, note 1415:88764; THL-120, THL-300).

Her nickname if she set one. Otherwise the bank plus the product, without
"Account", "Card", "®" or "*": "American Express Cobalt® Card" at American
Express is "Amex Cobalt". "••last4" is added only when two short names would
otherwise be the same.

Each account in the overview carries three fields from here:

- `short_name`: what a row shows ("Amex Cobalt", "TD Cash Back Visa ••1203").
- `short_bank`: the bank on its own ("Scotia iTRADE"), which AS-01 groups the
  accounts it leaves out of the budget by ("Scotia iTRADE · 3 accounts").
- `short_product`: the name without the bank ("Group RRSP"), listed under
  that grouped row.
"""

from __future__ import annotations

import re

# A bank's everyday name, for the long names banks and Plaid use.
_BANKS = {
    "american express": "Amex",
    "scotiabank": "Scotia",
    "the bank of nova scotia": "Scotia",
    "bank of nova scotia": "Scotia",
    "td canada trust": "TD",
    "td bank": "TD",
    "the toronto-dominion bank": "TD",
    "royal bank of canada": "RBC",
    "rbc royal bank": "RBC",
    "bank of montreal": "BMO",
    "canadian imperial bank of commerce": "CIBC",
}

_DROP_WORDS = re.compile(r"\b(?:accounts?|cards?)\b", re.I)
_DROP_MARKS = re.compile(r"[®™*]")
_SPACES = re.compile(r"\s+")


def _tidy(text: str) -> str:
    text = _DROP_MARKS.sub("", text or "")
    text = _DROP_WORDS.sub("", text)
    return _SPACES.sub(" ", text).strip(" -–—·,")


def short_bank(institution: str) -> str:
    """"American Express" → "Amex"; a name it doesn't know stays as it is."""
    name = _SPACES.sub(" ", (institution or "")).strip()
    return _BANKS.get(name.lower(), name)


def _strip_lead(product: str, lead: str) -> str | None:
    """The product without `lead` at its start (whole words), or None."""
    if lead and re.match(rf"{re.escape(lead)}\b", product, re.I):
        return product[len(lead):].strip(" -–—·,")
    return None


def split_name(product_name: str, institution: str = "") -> tuple[str, str]:
    """(bank, product): the bank's short name and what's left of the
    product once the bank and the extra words are gone."""
    product = _tidy(product_name)
    bank = short_bank(institution)
    if bank:
        for lead in (institution.strip(), bank):
            rest = _strip_lead(product, lead)
            if rest is not None:
                return bank, rest
        # A long bank name at the start of a product from another
        # institution's name ("Scotiabank Momentum" at "Scotia").
        for long, short in _BANKS.items():
            rest = _strip_lead(product, long)
            if rest is not None and short == bank:
                return bank, rest
        return bank, product
    # A statement or a balance added by hand: no bank but the name's own.
    for long, short in _BANKS.items():
        rest = _strip_lead(product, long)
        if rest is not None:
            return short, rest
    return "", product


def short_name(product_name: str, institution: str = "", nickname: str = "") -> str:
    if (nickname or "").strip():
        return nickname.strip()
    bank, product = split_name(product_name, institution)
    return " ".join(p for p in (bank, product) if p) or (product_name or "").strip() or "Account"


def add_short_names(rows: list[dict]) -> list[dict]:
    """Set `short_name`, `short_bank` and `short_product` on each account
    row (`bank_name` is its name without the mask, `institution`, `nickname`,
    `mask`), adding "••last4" where two would read the same."""
    for r in rows:
        nickname = (r.get("nickname") or "").strip()
        bank, product = split_name(r.get("bank_name") or r.get("name") or "", r.get("institution") or "")
        r["short_bank"] = bank
        r["short_name"] = nickname or short_name(r.get("bank_name") or r.get("name") or "",
                                                 r.get("institution") or "")
        r["short_product"] = nickname or product or r["short_name"]
    seen: dict[str, int] = {}
    for r in rows:
        key = r["short_name"].lower()
        seen[key] = seen.get(key, 0) + 1
    for r in rows:
        mask = (r.get("mask") or "").strip()
        # Her nickname is hers: it never gets digits added.
        if seen[r["short_name"].lower()] > 1 and mask and not (r.get("nickname") or "").strip():
            r["short_name"] = f"{r['short_name']} ••{mask}"
            r["short_product"] = f"{r['short_product']} ••{mask}"
    return rows
