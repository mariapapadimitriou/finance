"""Replay every detector over labelled ledgers and measure it (THL-310).

    python3 tests/eval/signals_replay.py        # the precision table

Two kinds of ledger:

* **The demo ledger** (sample_data/generate.py), built on a fixed day so the
  numbers don't move with the calendar. The generator knows what it put
  there: its subscriptions, bills, pay and travel are the labels.
* **Labelled fixtures** in tests/eval/fixtures/*.json: Plaid-shaped rows with
  the right answer for each. Real cases go there (anonymised), one file per
  story; see fixtures/README.md.

A detection is right (tp), wrong (fp) or unlabelled. Precision is
tp ÷ (tp + fp), per detector@version, None with nothing labelled. Free,
offline and deterministic: no model is called. test_signals_precision.py
holds each detector to a floor set from these numbers.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FIXTURES = os.path.join(HERE, "fixtures")
DEMO_TODAY = date(2026, 11, 15)


# ── Ledgers ──────────────────────────────────────────────────────────────

def _store(directory: str, name: str):
    from finance.store import Store
    return Store(os.path.join(directory, f"{name}.db"), url="")


def demo_store(directory: str):
    """The demo ledger as `python app.py --demo` loads it, on DEMO_TODAY."""
    import sample_data.generate as gen

    class Frozen(date):
        @classmethod
        def today(cls):
            return DEMO_TODAY

    st = _store(directory, "demo")
    real = gen.date
    gen.date = Frozen
    try:
        gen.load_demo(st)
    finally:
        gen.date = real
    return st


def fixture_store(directory: str, fx: dict):
    """A fixture's Plaid-shaped rows through the real importer."""
    from finance.ingest.base import IngestResult
    from finance.ingest.plaid_source import map_plaid_transaction
    from finance.pipeline import ingest

    st = _store(directory, fx["name"])
    accounts = {k: {"account_id": k, **v} for k, v in fx["accounts"].items()}
    rows = []
    for item in fx["transactions"]:
        t = map_plaid_transaction({"transaction_id": item["ref"], **item}, accounts)
        rows.append(t)
    ingest(st, IngestResult(transactions=rows), filename=f"{fx['name']}.json")
    # What she sorted herself, which the pattern detectors learn from.
    by_ref = {(t.raw or {}).get("plaid_id"): t.fingerprint for t in st.all_transactions()}
    for a in fx.get("answers") or []:
        st.set_transaction_category(by_ref[a["ref"]], a["category"])
    return st


def load_fixtures() -> list[dict]:
    out = []
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
                fx = json.load(fh)
            fx.setdefault("name", name[:-5])
            out.append(fx)
    return out


# ── Labels ───────────────────────────────────────────────────────────────

def _demo_judge(st):
    """What the generator put in the demo ledger, by descriptor."""
    import sample_data.generate as gen
    subs = {d for d, *_ in gen.SUBSCRIPTIONS}
    bills = {d for d, *_ in gen.FIXED_BILLS}
    pay = {gen.INCOME[0]}
    travel_words = ("UNITED AIRLINES", "MARRIOTT")
    desc = {t.fingerprint: t.description for t in st.all_transactions()}

    def judge(d) -> bool | None:
        texts = {desc.get(i, "") for i in d.txn_ids}
        if not texts:
            return None
        if d.detector == "recurring":
            if texts <= subs:
                return d.kind == "subscription"
            if texts <= bills:
                return d.kind == "bill"
            return False                      # nothing else in the demo recurs
        if d.detector in ("income.cadence", "income_bills.pay"):
            return texts <= pay
        if d.detector == "trips":
            return any(w in x for x in texts for w in travel_words)
        if d.detector in ("transfers.pairs", "duplicates", "recurring_transfers",
                          "income_bills.rent"):
            return False                      # the demo has none of these
        return None
    return judge


def _fixture_judge(st, fx: dict):
    """A detection is the label whose rows (and kind, when it says) match."""
    plaid_ids = {}
    for t in st.all_transactions():
        pid = (t.raw or {}).get("plaid_id")
        if pid:
            plaid_ids[t.fingerprint] = pid
    labels = fx.get("labels") or []
    exhaustive = set(fx.get("exhaustive") or [])

    def judge(d) -> bool | None:
        refs = {plaid_ids.get(i) for i in d.txn_ids}
        for lab in labels:
            if lab["detector"] != d.detector:
                continue
            # "subset": any run of the label's rows (pay within a lookback).
            same = (refs and refs <= set(lab["refs"])) if lab.get("match") == "subset" \
                else refs == set(lab["refs"])
            if not same:
                continue
            if lab.get("kind") and lab["kind"] != d.kind:
                return False
            return bool(lab["truth"])
        return False if d.detector in exhaustive else None
    return judge


# ── Replay ───────────────────────────────────────────────────────────────

@dataclass
class Score:
    detector: str
    version: str
    found: int = 0
    tp: int = 0
    fp: int = 0
    sources: set = field(default_factory=set)

    @property
    def labelled(self) -> int:
        return self.tp + self.fp

    @property
    def precision(self) -> float | None:
        return round(self.tp / self.labelled, 4) if self.labelled else None


def _tally(scores: dict, found: dict, judge, source: str) -> None:
    from finance.signals import DETECTORS
    for name, detections in found.items():
        s = scores.setdefault(name, Score(name, DETECTORS[name].version))
        for d in detections:
            s.found += 1
            verdict = judge(d)
            if verdict is None:
                continue
            s.sources.add(source)
            if verdict:
                s.tp += 1
            else:
                s.fp += 1


def replay(directory: str | None = None) -> dict[str, Score]:
    """Every detector over the demo ledger and every fixture."""
    from finance.signals import DETECTORS, run_all
    scores: dict[str, Score] = {n: Score(n, d.version) for n, d in DETECTORS.items()}
    with tempfile.TemporaryDirectory() if directory is None else _Keep(directory) as where:
        st = demo_store(where)
        _tally(scores, run_all(st, today=DEMO_TODAY.isoformat()), _demo_judge(st), "demo")
        for fx in load_fixtures():
            st = fixture_store(where, fx)
            _tally(scores, run_all(st, today=fx["today"]), _fixture_judge(st, fx), fx["name"])
    return scores


class _Keep:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self.path

    def __exit__(self, *exc):
        return False


def table(scores: dict[str, Score]) -> str:
    lines = [f"{'detector@version':<28} {'found':>5} {'tp':>4} {'fp':>4} {'precision':>9}  labelled by",
             "-" * 78]
    for name in sorted(scores):
        s = scores[name]
        p = "n/a" if s.precision is None else f"{s.precision:.2f}"
        lines.append(f"{name + '@' + s.version:<28} {s.found:>5} {s.tp:>4} {s.fp:>4} {p:>9}  "
                     f"{', '.join(sorted(s.sources)) or '-'}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table(replay()))
