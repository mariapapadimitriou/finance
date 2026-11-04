"""O-10s: how much of her pay she means to save."""
import json

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "ledger.db"))
    app.config["TESTING"] = True
    return app.test_client()


def test_saving_share_round_trip(client):
    client.put("/api/income-bills/expected", json={"amount": 4000})
    r = client.put("/api/income-bills/saving", json={"pct": 15})
    assert r.status_code == 200
    body = r.get_json()
    assert body["pct"] == 15
    assert body["monthly"] == 600
    assert client.get("/api/income-bills/saving").get_json()["pct"] == 15


def test_saving_share_out_of_range(client):
    assert client.put("/api/income-bills/saving", json={"pct": 80}).status_code == 400
    assert client.put("/api/income-bills/saving", json={"pct": "x"}).status_code == 400
