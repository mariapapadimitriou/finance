"""The bundled statements are the owner's card, and no other account's.

They were offered to every account in Settings → From a file, and loading
them copied the owner's statements into another ledger.
"""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture()
def accounts(tmp_path, monkeypatch):
    from app import create_app
    from finance import auth, users
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, "SPENDIE_SMTP_USER",
                "SPENDIE_SMTP_PASSWORD", "SPENDIE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("owner password"))
    app = create_app(str(tmp_path / "l.db"))
    owner = app.test_client()
    owner.post("/api/auth/login", json={"username": "mariapapas",
                                        "password": "owner password"})
    other = app.test_client()
    other.post("/api/auth/signup", json={"username": "anastasia",
                                         "password": "a long enough password"})
    return app, owner, other


def test_only_the_owner_sees_or_loads_them(accounts):
    _, owner, other = accounts
    assert owner.get("/api/import/bundled").get_json()["bundled"]
    assert other.get("/api/import/bundled").get_json()["bundled"] == []
    assert other.post("/api/import/bundled",
                      json={"key": "scotiabank_amex"}).status_code == 403
    assert other.get("/api/transactions").get_json()["transactions"] == []
    assert owner.post("/api/import/bundled",
                      json={"key": "scotiabank_amex"}).status_code == 200


def test_a_copy_already_in_another_account_is_removed(accounts):
    app, _, other = accounts
    # The state the bug left behind: the statements loaded into the other
    # account's ledger, beside a transaction of its own that shares nothing.
    from finance import users
    from finance.ingest import parse_csv
    from finance.pipeline import ingest
    from seed_data.bundled import read
    user = users.by_identifier(app.config["STORE"], "anastasia")
    st = app.config["STORE_FOR"](user)
    text, entry = read("scotiabank_amex")
    ingest(st, parse_csv(content=text, filename=entry["file"],
                         account_name=entry["account_name"],
                         account_id=entry["account_id"]),
           filename=f"{entry['label']} (bundled)")
    other.post("/api/transactions", json={
        "date": date.today().isoformat(), "description": "MY OWN COFFEE",
        "amount": 5, "category": "Coffee", "confirm": True})
    assert len(st.all_transactions()) > 1

    # Next time the ledger is opened (a new process), the copy goes.
    app.config["STORES"].clear()
    rows = other.get("/api/transactions").get_json()["transactions"]
    assert [r["description"] for r in rows] == ["MY OWN COFFEE"]
    assert not any("(bundled)" in (i.get("filename") or "")
                   for i in other.get("/api/imports").get_json().get("imports", []))


def test_the_owners_own_copy_stays(accounts):
    app, owner, _ = accounts
    owner.post("/api/import/bundled", json={"key": "scotiabank_amex"})
    n = len(owner.get("/api/transactions?limit=1000").get_json()["transactions"])
    app.config["STORES"].clear()
    assert len(owner.get("/api/transactions?limit=1000").get_json()["transactions"]) == n > 0
