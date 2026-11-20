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


def _out(value, shared: bool):
    return value if shared else copy.deepcopy(value)


def remember(key: tuple, compute: Callable[[], T], *, shared: bool = False) -> T:
    """`shared`: hand out the kept object itself (the caller copies what it
    needs, as `all_transactions` does row by row) instead of a deep copy."""
    g = _g()
    if g is None:
        return compute()
    cache = g.setdefault("_memo", {})
    hit = cache.get(key)
    if hit is not None and hit[0] == _seq():
        return _out(hit[1], shared)
    value = compute()
    # Noted after computing: a compute that writes (the review's one-time
    # fixes) is remembered against the state it left behind.
    cache[key] = (_seq(), value)
    return _out(value, shared)


# ── Across requests ──────────────────────────────────────────────────────
# The same answers, kept in the process between requests, for a ledger at
# one version (2026-11-19). A warm server instance answers Home, the list
# and Quick sort in a row for the same ledger; working the review and the
# ledger's rows out once for all three is most of their cost. An entry is
# keyed by the ledger's own id and its version, so a write anywhere (this
# instance or another) moves the version on and the entry is simply never
# asked for again; `today` is in the key where the answer depends on it.
# Only a request that hasn't written yet reads from here: after its own
# write the request-level memo above takes over. Bounded, newest kept.
_ACROSS: dict = {}
_ACROSS_SIZE = 64


def _clean() -> bool:
    return _seq() == (0, 0)


def remember_across(store, key: tuple, compute: Callable[[], T], *, rows_only: bool = False,
                    shared: bool = False) -> T:
    """`remember`, and between requests too. `rows_only`: the answer depends
    on the ledger's rows but not on settings, so a settings write this
    request doesn't spoil it. `shared`: as for `remember`."""
    g = _g()
    if g is None:
        return compute()
    seq = _seq()
    clean = seq == (0, 0) or (rows_only and seq[0] == 0)
    where = (store.path, store.url, store.schema)
    if not clean:
        # The request has written: its own memo serves it, and the ledger's
        # version needn't be read again after every write.
        return _out(remember(key + where, compute, shared=True), shared)
    ident = store.identity()
    full = ("across",) + ident + key
    hit = _ACROSS.get(full)
    if hit is not None:
        return _out(hit, shared)
    value = remember(key + where, compute, shared=True)
    if _seq() == seq:                    # computing it wrote nothing
        if len(_ACROSS) >= _ACROSS_SIZE:
            _ACROSS.pop(next(iter(_ACROSS)))
        _ACROSS[full] = value
    return _out(value, shared)


def forget_across() -> None:
    """Tests, and a store that was reset underneath a running process."""
    _ACROSS.clear()


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
