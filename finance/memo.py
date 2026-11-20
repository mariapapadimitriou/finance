"""Remember an answer for the rest of the request (2026-11-19).

Home, the list, Quick sort and the detail page each work out the review, the
kinds, the recurring charges and the Allowance from the whole ledger, and
within one request they ask for the same things several times over. An
answer is kept on `flask.g` until something is written (`store.dirty_seq`),
then worked out again. Outside a request nothing is kept.

Two kinds of key:

* `remember(key, compute)` for answers that depend only on the store and
  plain arguments (`review.for_store`). The key must name the store.
* `remember_for(txns, key, compute)` for answers about one list of
  transactions. The list is matched by identity and length, the way the
  recurring detector's memo did, because `all_transactions()` hands out a
  fresh list of copies every time and two lists with the same rows can
  differ in what a write just changed. The list is held for the request so
  its id stays its own.

Answers are deep-copied on the way out: callers add keys and sort lists in
place, and the next caller must not see that.
"""

from __future__ import annotations

import copy
from typing import Callable, TypeVar

T = TypeVar("T")


def _g():
    try:
        from flask import g, has_request_context
    except ImportError:                                           # pragma: no cover
        return None
    return g if has_request_context() else None


def _seq() -> tuple:
    from .store import dirty_seq, settings_seq
    return (dirty_seq(), settings_seq())


def remember(key: tuple, compute: Callable[[], T]) -> T:
    g = _g()
    if g is None:
        return compute()
    cache = g.setdefault("_memo", {})
    hit = cache.get(key)
    if hit is not None and hit[0] == _seq():
        return copy.deepcopy(hit[1])
    value = compute()
    # Noted after computing: a compute that writes (the review's one-time
    # fixes) is remembered against the state it left behind.
    cache[key] = (_seq(), value)
    return copy.deepcopy(value)


def remember_for(txns: list, key: tuple, compute: Callable[[], T]) -> T:
    g = _g()
    if g is None:
        return compute()
    cache = g.setdefault("_memo_lists", {})
    full = (id(txns), len(txns)) + key
    hit = cache.get(full)
    if hit is not None and hit[0] is txns and hit[1] == _seq():
        return copy.deepcopy(hit[2])
    value = compute()
    cache[full] = (txns, _seq(), value)
    return copy.deepcopy(value)
