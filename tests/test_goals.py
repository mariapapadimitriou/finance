"""Savings goals: a target, what is in it, what goes in each month."""

from __future__ import annotations

import pytest

from finance import goals


def goal(target=4000, saved=500, monthly=250):
    return {"id": 1, "name": "Japan", "target": target, "saved": saved,
            "monthly": monthly}


class TestTheMaths:
    def test_progress_and_landing_month(self):
        s = goals.status(goal(), "2026-10-05")
        assert s["progress"] == 0.125
        assert s["left"] == 3500
        assert s["months"] == 14
        assert s["eta"] == "2027-12"
        assert not s["reached"]

    def test_the_extra_lands_it_sooner(self):
        s = goals.status(goal(), "2026-10-05", extra=250)
        assert s["sooner"] == 7
        assert s["eta_with_extra"] == "2027-05"

    def test_nothing_going_in_never_lands(self):
        s = goals.status(goal(monthly=0), "2026-10-05")
        assert s["months"] is None and s["eta"] is None

    def test_a_reached_goal(self):
        s = goals.status(goal(saved=4000), "2026-10-05", extra=100)
        assert s["reached"] and s["progress"] == 1.0
        assert s["eta"] is None and s["sooner"] is None

    def test_funding_goes_to_goals_then_investing(self):
        f = goals.funding([goal(), goal(saved=4000, monthly=300)], 900)
        assert f == {"saving": 900, "to_goals": 250, "to_investing": 650, "over": 0}

    def test_funding_never_goes_below_zero(self):
        f = goals.funding([goal(monthly=1200)], 900)
        assert f["to_investing"] == 0 and f["over"] == 300


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "goals.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


class TestTheEndpoints:
    def test_create_deposit_and_reach(self, client):
        r = client.post("/api/goals", json={"name": "Japan", "target": 4000,
                                            "saved": 500, "monthly": 250})
        assert r.status_code == 201
        gid = r.get_json()["id"]
        body = client.get("/api/goals").get_json()
        assert body["goals"][0]["progress"] == 0.125
        assert body["to_goals"] == 250 and body["to_investing"] == 650

        body = client.post(f"/api/goals/{gid}/deposit",
                           json={"amount": 3500}).get_json()
        g = body["goals"][0]
        assert g["reached"] and g["reached_at"]
        # A reached goal takes nothing more from the month.
        assert body["to_goals"] == 0 and body["to_investing"] == 900

    def test_taking_money_back_out_unreaches_it(self, client):
        gid = client.post("/api/goals", json={"name": "Bike", "target": 100,
                                              "saved": 100}).get_json()["id"]
        body = client.post(f"/api/goals/{gid}/deposit",
                           json={"amount": -40}).get_json()
        assert not body["goals"][0]["reached"]
        assert body["goals"][0]["reached_at"] is None
        r = client.post(f"/api/goals/{gid}/deposit", json={"amount": -100})
        assert r.status_code == 400

    def test_edit_and_delete(self, client):
        gid = client.post("/api/goals", json={"name": "Bike", "target": 100}).get_json()["id"]
        body = client.patch(f"/api/goals/{gid}", json={"monthly": 25,
                                                       "name": "E-bike"}).get_json()
        assert body["goals"][0]["name"] == "E-bike"
        assert body["goals"][0]["monthly"] == 25
        assert client.delete(f"/api/goals/{gid}").status_code == 200
        assert client.get("/api/goals").get_json()["goals"] == []
        assert client.delete(f"/api/goals/{gid}").status_code == 404

    @pytest.mark.parametrize("body", [
        {"target": 100}, {"name": "X"}, {"name": "X", "target": 0},
        {"name": "X", "target": 100, "monthly": -5},
        {"name": "X", "target": "lots"}])
    def test_what_is_refused(self, client, body):
        assert client.post("/api/goals", json=body).status_code == 400

    def test_goals_survive_a_ledger_reset(self, client):
        client.post("/api/goals", json={"name": "Bike", "target": 100})
        client.application.config["STORE"].reset()
        assert len(client.get("/api/goals").get_json()["goals"]) == 1


def test_a_goal_belongs_to_its_own_account(tmp_path, monkeypatch):
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
    gid = maria.post("/api/goals", json={"name": "Japan", "target": 4000}).get_json()["id"]
    assert sister.get("/api/goals").get_json()["goals"] == []
    assert sister.delete(f"/api/goals/{gid}").status_code == 404
