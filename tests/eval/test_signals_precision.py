"""Detectors can't get worse (THL-310): precision per detector@version on
the demo ledger and the labelled fixtures, held to today's numbers.

The floors are what each detector scored on 2026-11-27. A new version may
score differently; give it its own floor here. Free and offline: no model
is called (the plan's paid evals run on demand, not here).
"""

import pytest

from signals_replay import replay, table

# detector@version: precision on 2026-11-27 (tp / labelled).
FLOORS = {
    "income.cadence@1": 1.00,         # 2 / 2
    "income_bills.pay@1": 1.00,       # 2 / 2
    "income_bills.rent@1": 1.00,      # 1 / 1
    "recurring@1": 1.00,              # 16 / 16 (the demo's subscriptions and bills)
    "recurring_transfers@1": 1.00,    # 1 / 1
    "duplicates@1": 1.00,             # 1 / 1
    # Pairs a friend's e-Transfer in with another's out for the same amount
    # (fixtures/transfers_and_card_payments.json): the kind of mistake real
    # cases will show. Phase 4 (THL-309) fixes it under a new version.
    "transfers.pairs@1": 0.66,        # 2 / 3
    # A pattern at a shop that sells everything (fixtures/her_answers.json):
    # her Yes is what keeps it from sorting (AI detects, she confirms).
    "pattern_sort.category@1": 0.50,  # 1 / 2
}


@pytest.fixture(scope="module")
def scores(tmp_path_factory):
    found = replay(str(tmp_path_factory.mktemp("signals_eval")))
    print("\n" + table(found))
    return found


@pytest.mark.parametrize("tag", sorted(FLOORS))
def test_precision_holds(scores, tag):
    name, version = tag.split("@")
    s = scores[name]
    assert s.version == version, f"{name} is at @{s.version}: give the new version its own floor"
    assert s.precision is not None, f"{tag} has nothing labelled any more"
    assert s.precision >= FLOORS[tag], f"{tag}: {s.precision} < {FLOORS[tag]}\n{table(scores)}"


def test_every_labelled_detector_has_a_floor(scores):
    """A labelled case for a detector without a floor would gate nothing."""
    labelled = {f"{n}@{s.version}" for n, s in scores.items() if s.labelled}
    assert labelled <= set(FLOORS), sorted(labelled - set(FLOORS))
