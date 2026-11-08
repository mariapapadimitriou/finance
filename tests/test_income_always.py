"""Always for a payer, on income (2026-11-08): the kind of income, remembered."""

import pytest

from finance import secrets_box
from finance.pipeline import classify_ledger
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, october, tx


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "ia.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def ids(c):
    return {(t.merchant, t.date[:10]): t.fingerprint for t in c.st.all_transactions()}


def kind(c, tid):
    return next(t for t in c.st.all_transactions() if t.fingerprint == tid).income_type


def test_always_counts_the_payers_deposits_as_that_kind(client):
    client.st.add_transactions(history() + october() + [
        tx("2026-10-05", "Rose Papas", -100.0, "Income"),
        tx("2026-09-05", "Rose Papas", -80.0, "Income")])
    classify_ledger(client.st)
    first = ids(client)[("Rose Papas", "2026-10-05")]
    other = ids(client)[("Rose Papas", "2026-09-05")]
    row = client.get(f"/api/transactions/{first}").get_json()
    assert row["income_rule"] == {"payer": "Rose Papas", "on": False}
    client.put(f"/api/transactions/{first}/income-type", json={"kind": "gifts"})
    r = client.put(f"/api/transactions/{first}/income-always", json={"on": True}).get_json()
    assert r["ok"] and r["on"]
    assert kind(client, other) == "gifts"
    assert client.get(f"/api/transactions/{other}").get_json()["income_rule"]["on"]
    # A new one from her arrives already counted as a gift.
    client.st.add_transactions([tx("2026-10-20", "Rose Papas", -50.0, "Other")])
    classify_ledger(client.st)
    new = ids(client)[("Rose Papas", "2026-10-20")]
    assert kind(client, new) == "gifts"
    assert next(t for t in client.st.all_transactions() if t.fingerprint == new).category == "Income"
    # Changing one's kind with Always on moves the rule with it.
    client.put(f"/api/transactions/{first}/income-type", json={"kind": "other"})
    client.st.add_transactions([tx("2026-10-25", "Rose Papas", -40.0, "Income")])
    classify_ledger(client.st)
    assert kind(client, ids(client)[("Rose Papas", "2026-10-25")]) == "other"
    # Off: the rule goes, what it sorted stays.
    r = client.put(f"/api/transactions/{first}/income-always", json={"on": False}).get_json()
    assert not r["on"] and kind(client, other) == "gifts"
    assert not client.get(f"/api/transactions/{first}").get_json()["income_rule"]["on"]


def test_a_name_every_transfer_shares_cannot_have_always(client):
    client.st.add_transactions([tx("2026-10-05", "Interac e-Transfer", -100.0, "Income")])
    tid = ids(client)[("Interac e-Transfer", "2026-10-05")]
    assert client.get(f"/api/transactions/{tid}").get_json()["income_rule"]["payer"] is None
    assert client.put(f"/api/transactions/{tid}/income-always", json={"on": True}).status_code == 400
