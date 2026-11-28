"""Smart ships only if it doesn't lower precision (THL-309 AC 14).

Rules and Smart replay the same new purchases (smart_replay.py) with a fake
model: free, offline and deterministic. On 2026-11-28 Rules answered 4 of 7
right (0.57) and Smart 6 of 7 (0.86); both sorted the same 2 by themselves.
"""

import pytest

from smart_replay import replay, table


@pytest.fixture(scope="module")
def scores():
    found = replay()
    print("\n" + table(found))
    return found


def test_smart_is_no_less_precise_than_rules(scores):
    rules, smart = scores["rules"], scores["smart"]
    assert rules.precision is not None and smart.precision is not None
    assert smart.precision >= rules.precision, table(scores)


def test_smart_never_sorts_more_by_itself(scores):
    # Python's gate and her Yes decide what sorts; Claude can only hold one back.
    assert scores["smart"].auto <= scores["rules"].auto
    assert (scores["smart"].auto_precision or 0) >= (scores["rules"].auto_precision or 0)


def test_floors(scores):
    assert scores["rules"].precision >= 0.57
    assert scores["smart"].precision >= 0.85
