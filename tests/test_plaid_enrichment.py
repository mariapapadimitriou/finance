"""Free with every Plaid transaction: a logo, a stable merchant id and how
sure Plaid is of its category."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.ingest.plaid_source import map_plaid_transaction
from finance.pipeline import ingest


def item(tid, name, entity="ent-uber", confidence="VERY_HIGH", primary="FOOD_AND_DRINK"):
    return {"transaction_id": tid, "date": "2026-10-02", "name": name, "amount": 25,
            "account_id": "card", "iso_currency_code": "CAD", "merchant_entity_id": entity,
            "logo_url": "https://plaid-merchant-logos.plaid.com/uber.png",
            "personal_finance_category": {"primary": primary, "confidence_level": confidence}}


ACCTS = {"card": {"type": "credit", "subtype": "credit card", "name": "Visa", "mask": "1"}}


def test_the_fields_are_kept():
    t = map_plaid_transaction(item("a", "UBER EATS"), ACCTS)
    assert t.raw["logo_url"].endswith("uber.png")
    assert t.raw["merchant_entity_id"] == "ent-uber"
    assert t.raw["category_confidence"] == "VERY_HIGH"


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "e.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def load(c, *items):
    st = c.application.config["STORE"]
    ingest(st, IngestResult([map_plaid_transaction(i, ACCTS) for i in items], "card"))
    return st


def test_a_correction_follows_the_merchant_whatever_its_name(client):
    st = load(client, item("a", "UBER EATS TORONTO"))
    row = st.all_transactions()[0]
    client.patch(f"/api/transactions/{row.fingerprint}",
                 json={"category": "Food Delivery", "apply_to_merchant": True})
    load(client, item("b", "UBER *EATS PENDING"))
    cats = {t.description: t.category for t in st.all_transactions()}
    assert cats["UBER *EATS PENDING"] == "Food Delivery"


def test_rows_carry_the_logo(client):
    load(client, item("a", "UBER EATS"))
    row = client.get("/api/transactions").get_json()["transactions"][0]
    assert row["logo"].endswith("uber.png")


def test_not_sure_lists_what_plaid_doubted(client):
    load(client, item("a", "ZZQ MART", entity="", confidence="LOW", primary="GENERAL_MERCHANDISE"),
         item("b", "ACME HARDWARE", entity="", confidence="VERY_HIGH", primary="HOME_IMPROVEMENT"))
    body = client.get("/api/transactions?category=__unsure__").get_json()
    assert [t["description"] for t in body["transactions"]] == ["ZZQ MART"]
    assert body["transactions"][0]["unsure"] is True
    # Once you say what it is, it's no longer in doubt.
    client.patch(f"/api/transactions/{body['transactions'][0]['id']}", json={"category": "Shopping"})
    assert client.get("/api/transactions?category=__unsure__").get_json()["total"] == 0
