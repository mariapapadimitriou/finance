"""P3 / P4 (TP-P3-NoGuess, TP-P4-QuickSort): the four likeliest categories
for one purchase, from her own ledger, as tiles she taps. Never an
auto-sort, never a fixed list of shops, and no AI: in order,

1. what she picked for the same merchant;
2. what she picked for purchases whose names share a distinctive word
   ("Lucky Noodle Bar" and "TST* Lucky Noodle");
3. the bank's own category (Plaid's `personal_finance_category`, detailed
   then its group's others);
4. her most used overall, to fill up to four.

Only spending categories she can pick: not hidden, not Other, not a state
Pearl puts a row in.
"""

from __future__ import annotations

import re
from collections import Counter

from .categorize import (CATEGORIES, PLAID_CATEGORY_MAP, _TRANSFER_WORDS, bank_category, group_of,
                         is_generic_transfer_name, merchant_key)
from .models import Transaction

COUNT = 4
# A pick is hers when she made it: by hand, by a range or pattern she
# sorted, or by a rule she saved for the merchant.
_HERS = {"user", "range", "pattern", "merchant_override"}
_NOT_PICKABLE = {"Other", "Unsorted transfers"}


def pickable(hidden: set[str] | None = None) -> list[str]:
    """The spending categories a tile can be, in the list's order."""
    hidden = hidden or set()
    return [c for c in CATEGORIES
            if group_of(c) in ("essentials", "lifestyle") and c not in _NOT_PICKABLE and c not in hidden]


def _words(t: Transaction) -> set[str]:
    text = f"{t.merchant or ''} {t.description or ''}".lower()
    return {w for w in re.split(r"[^a-z]+", text)
            if len(w) >= 3 and w not in _TRANSFER_WORDS}


class Index:
    """Her picks, worked out once for many purchases (Needs a look, Quick sort)."""

    def __init__(self, transactions: list[Transaction], hidden: set[str] | None = None):
        self.allowed = pickable(hidden)
        ok = set(self.allowed)
        self.uses = Counter(t.category for t in transactions if t.category in ok)
        self.by_merchant: dict[str, Counter] = {}
        self.by_word: dict[str, Counter] = {}
        merchants_with: dict[str, set[str]] = {}
        all_merchants: set[str] = set()
        for t in transactions:
            k = merchant_key(t.merchant or "")
            if k:
                all_merchants.add(k)
                for w in _words(t):
                    merchants_with.setdefault(w, set()).add(k)
            if t.amount <= 0 or t.category not in ok or t.category_source not in _HERS:
                continue
            if k and not is_generic_transfer_name(t.merchant):
                self.by_merchant.setdefault(k, Counter())[t.category] += 1
            for w in _words(t):
                self.by_word.setdefault(w, Counter())[t.category] += 1
        # A word is distinctive when few of her merchants share it: "noodle",
        # not "store" or her city.
        cap = max(3, len(all_merchants) // 50)
        self.distinctive = {w for w, ms in merchants_with.items() if len(ms) <= cap}

    def likeliest(self, t: Transaction, count: int = COUNT) -> list[str]:
        out: list[str] = []

        def add(names):
            for n in names:
                if n in self.allowed and n not in out:
                    out.append(n)

        k = merchant_key(t.merchant or "")
        if k and not is_generic_transfer_name(t.merchant):
            add(n for n, _ in (self.by_merchant.get(k) or Counter()).most_common())
        similar = Counter()
        for w in _words(t) & self.distinctive:
            similar.update(self.by_word.get(w) or {})
        add(n for n, _ in similar.most_common())
        add(bank_hints((t.raw or {}).get("issuer_category", "")))
        ranked = sorted(self.allowed, key=lambda n: (-self.uses.get(n, 0), self.allowed.index(n)))
        add(ranked)
        return out[:count]


def bank_hints(code: str) -> list[str]:
    """The bank's category, then the others in its Plaid group (a coffee
    shop's FOOD_AND_DRINK_COFFEE, then Dining, Groceries, Alcohol & Bars)."""
    code = (code or "").strip().upper().replace(" ", "_")
    if not code:
        return []
    out = []
    first = bank_category(code)
    if first:
        out.append(first)
    # Its Plaid group: the shortest code in the map it starts with.
    groups = [k for k in PLAID_CATEGORY_MAP if code == k or code.startswith(k + "_")]
    primary = min(groups, key=len) if groups else None
    if primary:
        for k, v in PLAID_CATEGORY_MAP.items():
            if (k == primary or k.startswith(primary + "_")) and v not in out:
                out.append(v)
    return out


def likeliest(t: Transaction, transactions: list[Transaction], hidden: set[str] | None = None,
              count: int = COUNT) -> list[str]:
    return Index(transactions, hidden).likeliest(t, count)


def annotate(st, review: dict, txns: list[Transaction]) -> None:
    """Add `likely` to each What was this? question in Needs a look (and so
    Quick sort): her four likeliest for that purchase."""
    items = review.get("unsure_category") or []
    if not items:
        return
    from .marks import hidden_categories
    index = Index(txns, hidden_categories(st))
    by_id = {t.fingerprint: t for t in txns}
    for it in items:
        t = by_id.get(it["txn"]["id"])
        if t is not None:
            it["likely"] = index.likeliest(t)
