"""Her savings % is set aside on its own (product owner, 2026-11-26).

The share of her pay she chose in set-up (O-10s, `savings_rate`) comes off
the Allowance as a Saving line in How it adds up (the "saved" row), between
Bills and the Allowance:

* the target is that share of the month's income, the income row the
  Allowance already starts from;
* money she actually moved to savings this month counts toward it, so the
  line is the larger of the two and nothing comes off twice;
* 0% or no share: no target, only money actually moved comes off (THL-230,
  as before);
* Allowance, spent, zone and Left stay one sum, on Home, Cash flow (which
  reads Home's) and the month picker.
"""

from __future__ import annotations

import sys
import pytest

from finance import safe_to_spend as sts

sys.path.insert(0, "tests")

from test_safe_to_spend import TODAY, history, october  # noqa: E402


def _row(out, key):
    return next(r for r in out["rows"] if r["key"] == key)


def _plain():
    """October to the 9th: $4,300 in, and $150 already moved to savings."""
    return history() + [t for t in october() if t.my_share is None and not t.repays]


def _before_saving(out) -> float:
    """The number with nothing at all taken off for saving."""
    return out["amount"] + out["saving"]


# ── The rule ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rate, moved_c, amount_c, target_c", [
    (0.10, 0, 30000, 30000),          # nothing moved: the whole target
    (0.10, 10000, 30000, 30000),      # $100 moved counts toward $300
    (0.10, 50000, 50000, 30000),      # $500 moved: more than the target
    (0.10, 30000, 30000, 30000),      # exactly the target: once, not twice
    (0.0, 12000, 12000, 0),           # no share: only what was moved
    (None, 0, 0, 0),                  # no share, nothing moved: nothing
])
def test_saving_is_the_larger_of_target_and_moved(rate, moved_c, amount_c, target_c):
    row = sts.saving_row(300000, rate, moved_c)
    assert row["key"] == "saved"
    assert row["amount_c"] == amount_c
    assert row["target"] == target_c / 100
    assert row["moved"] == moved_c / 100
    assert row["rate"] == (rate or None)


def test_target_rounds_to_the_cent_and_ignores_negative_income():
    assert sts.saving_row(123456, 0.125, 0)["amount_c"] == 15432   # 15432.0
    assert sts.saving_row(100001, 0.05, 0)["amount_c"] == 5000     # 5000.05
    assert sts.saving_row(-5000, 0.1, 0)["amount_c"] == 0
    assert sts.saving_row(100000, 0.1, -500)["moved"] == 0.0


# ── In the Allowance ──────────────────────────────────────────────────────

def test_the_share_comes_off_the_allowance():
    txns = _plain()
    base = sts.compute(txns, TODAY)
    out = sts.compute(txns, TODAY, saving_rate=0.10)
    income = _row(out, "income")["amount"]
    target = round(income * 0.10, 2)
    assert out["saving_rate"] == 0.10
    assert out["saving_target"] == target
    assert out["saving"] == _row(out, "saved")["amount"] == target
    assert base["saving_moved"] == 150 and target > 150
    assert out["amount"] == pytest.approx(_before_saving(base) - target, abs=0.01)
    # The rows still add up to the number, to the cent.
    rows = out["rows"]
    total = rows[0]["amount"] - sum(r["amount"] for r in rows[1:] if r["key"] != "from_last_month")
    total += sum(r["amount"] for r in rows if r["key"] == "from_last_month")
    assert out["amount"] == pytest.approx(total, abs=0.001)


def test_saving_sits_between_bills_and_the_allowance():
    out = sts.compute(_plain(), TODAY, saving_rate=0.10)
    keys = [r["key"] for r in out["rows"]]
    assert keys.index("bills") < keys.index("saved")


def test_money_moved_to_savings_is_not_taken_off_twice():
    txns = _plain()
    base = sts.compute(txns, TODAY)
    income = _row(base, "income")["amount"]
    target = round(income * 0.10, 2)
    # Moved less than the target: the target comes off, once.
    some = sts.compute(txns, TODAY, saving_rate=0.10, moved_to_savings=target / 2)
    assert some["saving"] == target and some["saving_moved"] == round(target / 2, 2)
    assert some["amount"] == pytest.approx(_before_saving(base) - target, abs=0.01)
    # Moved more than the target: what she moved comes off, no more.
    lots = sts.compute(txns, TODAY, saving_rate=0.10, moved_to_savings=target + 200)
    assert lots["saving"] == pytest.approx(target + 200)
    assert lots["amount"] == pytest.approx(_before_saving(base) - target - 200, abs=0.01)


def test_no_share_changes_nothing():
    txns = _plain()
    base = sts.compute(txns, TODAY)
    for rate in (0.0, None):
        out = sts.compute(txns, TODAY, saving_rate=rate)
        assert out["amount"] == base["amount"]
        assert out["saving_rate"] is None and out["saving_target"] == 0.0
    # Only what she moved comes off, as before (THL-230).
    assert base["saving"] == base["saving_moved"] == 150
    none = sts.compute(txns, TODAY, moved_to_savings=0)
    assert none["saving"] == 0 and none["amount"] == pytest.approx(base["amount"] + 150, abs=0.01)


def test_the_gauge_takes_the_saving_out_of_the_allowance_not_spent():
    txns = _plain()
    base = sts.compute(txns, TODAY)
    out = sts.compute(txns, TODAY, saving_rate=0.10)
    assert out["spent"] == base["spent"]
    extra = out["saving"] - base["saving"]
    assert out["allowance"] == pytest.approx(base["allowance"] - extra, abs=0.01)
    assert out["allowance"] == pytest.approx(out["shown"] + out["spent"], abs=0.01)


def test_a_big_share_can_put_her_over():
    """$4,300 in: 50% is $2,150, of which the $150 she moved is part, so
    $2,000 more comes off $682.18: over by $1,317.82."""
    out = sts.compute(_plain(), TODAY, saving_rate=0.5)
    assert out["state"] == "over" and out["zone"] == "over"
    assert out["over_by"] == pytest.approx(2000 - 682.18, abs=0.01)
    assert out["shown"] == out["amount"] == -out["over_by"]


def test_needs_income_has_no_saving():
    out = sts.compute([], TODAY, saving_rate=0.10)
    assert out["state"] == "needs_income"
    assert out["saving"] is None and out["saving_rate"] is None


# ── Through the API: Home, the picker, set-up's choice ───────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    app = create_app(str(tmp_path / "saving.db"))
    app.config.update(TESTING=True)
    app.config["STORE"].add_transactions(_plain())
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def _home(c):
    return c.get("/api/home").get_json()["safe_to_spend"]


def test_choosing_a_share_in_set_up_moves_homes_allowance(client):
    before = _home(client)
    assert before["saving_rate"] is None
    r = client.put("/api/income-bills/saving", json={"pct": 10})
    assert r.status_code == 200
    after = _home(client)
    income = _row(after, "income")["amount"]
    assert after["saving_rate"] == 0.1
    assert after["saving"] == round(income * 0.1, 2)
    assert after["amount"] == pytest.approx(_before_saving(before) - after["saving"], abs=0.01)
    # Back to 0%: the line goes, the Allowance comes back.
    client.put("/api/income-bills/saving", json={"pct": 0})
    again = _home(client)
    assert again["saving_rate"] is None and again["amount"] == before["amount"]


def test_the_month_picker_shows_homes_left_with_the_saving(client):
    client.put("/api/income-bills/saving", json={"pct": 10})
    home = _home(client)
    months = client.get("/api/transactions/months").get_json()["months"]
    [now] = [m for m in months if m["month"] == home["month"]]
    assert now["allowance"] is True
    left = -home["over_by"] if home["state"] == "over" else home["shown"]
    assert now["left"] == left


def test_the_old_savings_target_alone_takes_nothing_off(client):
    """`savings_target` (Goals' saving goal, the old weekly plan) is not
    the share: only `savings_rate` sets money aside on Home."""
    before = _home(client)
    client.st.set_setting("savings_target", "300")
    assert _home(client)["amount"] == before["amount"]

