"""Every detector, its version and the kinds it finds (THL-310).

A version moves on whenever what a detector finds could change (a new
threshold, a new signal): outcomes are recorded against detector@version,
so the accuracy of the old and the new can be told apart. Phase 4 (THL-309)
adds detectors here; it never edits an old version's numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import adapters


def _smart(st, txns, today, version):
    from .. import smart_sort
    return smart_sort.detections(st, version)


@dataclass(frozen=True)
class Detector:
    name: str
    version: str
    kinds: tuple[str, ...]
    module: str                 # what it wraps
    run: Callable
    reads_review: bool = False  # answers questions in Needs a look


DETECTORS: dict[str, Detector] = {d.name: d for d in (
    Detector("pattern_sort.category", "1", ("category_pattern",), "finance/pattern_sort.py",
             adapters.pattern_sort),
    Detector("pattern_sort.joint", "1", ("joint_theirs",), "finance/pattern_sort.py",
             adapters.pattern_sort),
    # Phase 4 (THL-309): Smart's picks, each made once, right after a sync.
    Detector("smart_sort", "1", ("category_pattern",), "finance/smart_sort.py",
             _smart),
    Detector("likely", "1", ("category_pattern",), "finance/likely.py", adapters.likely,
             reads_review=True),
    Detector("recurring", "1", ("subscription", "bill"), "finance/insights/recurring.py",
             adapters.recurring),
    Detector("recurring_transfers", "1", ("bill",), "finance/recurring_transfers.py",
             adapters.recurring_transfers),
    Detector("income.cadence", "1", ("income",), "finance/income.py", adapters.income),
    Detector("income_bills.pay", "1", ("income",), "finance/income_bills.py",
             adapters.income_bills_pay),
    Detector("income_bills.rent", "1", ("bill",), "finance/income_bills.py",
             adapters.income_bills_rent),
    Detector("income_kind_rules", "1", ("income",), "finance/income_kind_rules.py",
             adapters.income_kind_rules),
    Detector("trips", "1", ("trip",), "finance/trips.py", adapters.trips),
    Detector("transfers.pairs", "1", ("transfer_pair", "card_payment"), "finance/transfers.py",
             adapters.transfers),
    Detector("pairs", "1", ("payback",), "finance/pairs.py", adapters.pairs, reads_review=True),
    Detector("etransfers.party", "1", ("party",), "finance/etransfers.py", adapters.etransfers),
    Detector("joint.payback_offer", "1", ("joint_theirs",), "finance/joint.py", adapters.joint),
    Detector("duplicates", "1", ("duplicate",), "finance/duplicates.py", adapters.duplicates),
)}


def version_of(detector: str) -> str:
    d = DETECTORS.get(detector)
    return d.version if d else "0"


def run(name: str, st, txns=None, today: str | None = None, review=None) -> list:
    """One detector's detections. pattern_sort's two share one adapter:
    each keeps its own."""
    from datetime import date
    d = DETECTORS[name]
    txns = st.all_transactions() if txns is None else txns
    today = today or date.today().isoformat()
    if d.reads_review:
        found = d.run(st, txns, today, d.version, review=review)
    else:
        found = d.run(st, txns, today, d.version)
    return [x for x in found if x.detector == name]


def run_all(st, txns=None, today: str | None = None, names=None) -> dict[str, list]:
    """{detector: [Detection]} for every detector (or those named). The
    Needs a look review is worked out once for the two that read it."""
    txns = st.all_transactions() if txns is None else txns
    review = None
    out = {}
    for name in names or DETECTORS:
        if DETECTORS[name].reads_review and review is None:
            from datetime import date
            from ..review import for_store
            review = for_store(st, today or date.today().isoformat())
        out[name] = run(name, st, txns, today, review=review)
    return out
