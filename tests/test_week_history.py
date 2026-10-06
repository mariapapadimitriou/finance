"""The arrows on the Allowance card: any past week, as it finished."""

from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "weeks.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


def charge(c, when: date, amount: float, category="Dining"):
    r = c.post("/api/transactions", json={
        "date": when.isoformat(), "description": f"SPEND {when}", "amount": amount,
        "category": category, "confirm": True})
    assert r.status_code == 200, r.get_json()


def week(c, on: date):
    return c.get(f"/api/plan/week?on={on.isoformat()}")


def last_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


def test_a_past_week_shows_what_it_ended_on(client):
    today = date.today()
    monday = last_monday(today) - timedelta(days=14)      # two weeks ago
    charge(client, monday, 40)
    charge(client, monday + timedelta(days=2), 25)
    charge(client, monday + timedelta(days=3), 80, category="Groceries")   # not weekly
    body = week(client, monday + timedelta(days=1)).get_json()
    w = body["week"]
    assert body["done"] is True
    # Clipped to the month, so a week can start after the Monday.
    inside = [d for d in (monday, monday + timedelta(days=2))
              if d.month == date.fromisoformat(f"{body['month']}-01").month]
    assert w["spent"] == pytest.approx(sum(40 if d == monday else 25 for d in inside))
    assert w["left"] == pytest.approx(w["allowance"] - w["spent"], abs=0.01)


def test_the_week_before_a_months_first_is_the_last_of_the_one_before(client):
    first = date.today().replace(day=1)
    charge(client, first - timedelta(days=40), 10)           # some earlier history
    body = week(client, first).get_json()
    assert body["week"]["first_day"] == 1
    assert body["previous"] == (first - timedelta(days=1)).isoformat()
    prev = week(client, date.fromisoformat(body["previous"])).get_json()
    assert prev["month"] == (first - timedelta(days=1)).strftime("%Y-%m")
    assert prev["week"]["last_day"] == (first - timedelta(days=1)).day


def test_the_ends_of_the_road(client):
    today = date.today()
    live_start = today.replace(day=max(today.day - today.weekday(), 1))
    charge(client, live_start - timedelta(days=3), 10)
    before_live = week(client, live_start - timedelta(days=1)).get_json()
    assert before_live["next"] is None          # the live card has the next one
    oldest = week(client, live_start - timedelta(days=3)).get_json()
    assert oldest["previous"] is None or oldest["previous"] >= (
        live_start - timedelta(days=3)).isoformat()


@pytest.mark.parametrize("on", ["tomorrow", "2026-13-01", ""])
def test_bad_dates_are_refused(client, on):
    if on == "tomorrow":
        on = (date.today() + timedelta(days=1)).isoformat()
    assert client.get(f"/api/plan/week?on={on}").status_code == 400


def test_each_account_sees_its_own_weeks(tmp_path, monkeypatch):
    from app import create_app
    from finance import auth, users
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, "SPENDIE_SMTP_USER",
                "SPENDIE_SMTP_PASSWORD", "SPENDIE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("owner password"))
    app = create_app(str(tmp_path / "l.db"))
    maria = app.test_client()
    maria.post("/api/auth/login", json={"username": "mariapapas",
                                        "password": "owner password"})
    sister = app.test_client()
    sister.post("/api/auth/signup", json={"username": "sister",
                                          "password": "a long enough password"})
    day = date.today() - timedelta(days=10)
    charge(maria, day, 55)
    assert week(maria, day).get_json()["week"]["spent"] >= 55
    assert week(sister, day).get_json()["week"]["spent"] == 0
