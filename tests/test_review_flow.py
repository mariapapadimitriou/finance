"""Changing a category and sorting a transfer say what they did, and can be
undone — rules included (THL-123, THL-163)."""

from __future__ import annotations

from datetime import date

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]


def today(d=None):
    return TODAY.isoformat() if d is None else f"{MONTH}-{d:02d}"


def row(amount, description, account="card", kind="credit", category=None, who=None,
        merchant=None, when=None):
    raw = {"account_type": kind}
    if who:
        raw["counterparty"] = who
    t = Transaction(date=when or today(), description=description, amount=amount,
                    account_id=account, account_name=account, raw=raw,
                    merchant=merchant or "")
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "review.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.set_setting("monthly_income", 4000)
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t.fingerprint for t in st.all_transactions()}


def cat(st, tid):
    return st.get_transaction(tid).category


def test_preview_matches_what_saving_does(client):
    ids = load(client.st, row(60, "SUSHI NAMI", category="Dining"))
    tid = ids["SUSHI NAMI"]
    pre = client.post(f"/api/transactions/{tid}/category/preview",
                      json={"category": "Saved"}).get_json()
    assert cat(client.st, tid) == "Dining", "a preview writes nothing"
    # The week's number is the app's own arithmetic, so only its direction is
    # asserted here; what matters is that the preview and the save agree.
    assert pre["delta"] > 0 and pre["group_to"] == "savings"
    assert pre["line"] == (f"Your safe to spend goes up by ${pre['delta']:,.2f}, because "
                           "it went to savings, not spending.")
    done = client.patch(f"/api/transactions/{tid}", json={"category": "Saved"}).get_json()
    assert done["impact"]["after"] == pre["after"]
    assert done["impact"]["delta"] == pre["delta"]
    assert done["impact"]["title"] == f"Safe to spend is now ${pre['after']:,.2f}."
    assert cat(client.st, tid) == "Saved"


def test_same_group_says_it_stays_the_same(client):
    ids = load(client.st, row(6, "CAFE", category="Dining"))
    pre = client.post(f"/api/transactions/{ids['CAFE']}/category/preview",
                      json={"category": "Coffee"}).get_json()
    assert pre["delta"] == 0
    assert pre["line"] == "Both are Lifestyle, so your safe to spend stays the same."
    same = client.post(f"/api/transactions/{ids['CAFE']}/category/preview",
                       json={"category": "Dining"}).get_json()
    assert same["line"] == "", "nothing to say about the category it already has"


def test_apply_to_all_counts_and_undo_takes_the_rule_back(client):
    ids = load(client.st,
               row(24.8, "UBER EATS 1", merchant="Uber Eats"),
               row(31.2, "UBER EATS 2", merchant="Uber Eats", when=today(1)),
               row(12.0, "UBER EATS 3", merchant="Uber Eats", when=today(2)),
               row(40, "LOBLAWS", merchant="Loblaws"))
    first = ids["UBER EATS 1"]
    before = {i: cat(client.st, i) for i in ids.values()}
    pre = client.post(f"/api/transactions/{first}/category/preview",
                      json={"category": "Dining", "apply_to_merchant": True}).get_json()
    assert pre["merchant_count"] == 3
    done = client.patch(f"/api/transactions/{first}",
                        json={"category": "Dining", "apply_to_merchant": True}).get_json()
    assert done["scope"] == "merchant"
    assert {cat(client.st, ids[f"UBER EATS {n}"]) for n in (1, 2, 3)} == {"Dining"}
    assert "uber eats" in client.st.overrides()
    assert done["undo"]["overrides"] == {"uber eats": None}

    res = client.post("/api/transactions/undo", json=done["undo"])
    assert res.status_code == 200, res.get_json()
    assert "uber eats" not in client.st.overrides()
    assert {i: cat(client.st, i) for i in ids.values()} == before


def test_sorting_a_transfer_with_remember_and_undo(client):
    ids = load(client.st, row(200, "SEND E-TFR ***X", account="chq", kind="depository",
                              who="M. Papas"))
    tid = ids["SEND E-TFR ***X"]
    assert cat(client.st, tid) == "Unsorted transfers"
    done = client.post("/api/transfers/sort", json={
        "ids": [tid], "category": "Saved", "remember": True}).get_json()
    assert done["learned"] == 1 and cat(client.st, tid) == "Saved"
    imp = done["impact"]
    # Until it was sorted it counted as spent, safe to spend included.
    assert imp["spent_delta"] == -200 and imp["delta"] > 0
    assert imp["detail"] == (f"${imp['delta']:,.2f} more, because it went to savings, "
                             "not spending.")
    assert client.st.destinations(), "Remember wrote a rule"

    assert client.post("/api/transactions/undo", json=done["undo"]).status_code == 200
    assert not client.st.destinations(), "Undo removed the rule"
    assert cat(client.st, tid) == "Unsorted transfers"


def test_moved_between_my_own_accounts(client):
    ids = load(client.st, row(500, "SEND E-TFR ***Y", account="chq", kind="depository",
                              who="Maria P"))
    tid = ids["SEND E-TFR ***Y"]
    done = client.post("/api/transfers/sort", json={
        "ids": [tid], "category": "Transfers"}).get_json()
    assert cat(client.st, tid) == "Transfers"
    assert done["impact"]["spent_delta"] == -500
    assert not client.st.destinations(), "no rule without Remember"


@pytest.mark.parametrize("category", ["Dining", "Rent & Housing", "Saved", "Transfers"])
def test_sorting_never_lowers_safe_to_spend(client, category):
    ids = load(client.st, row(150, "SEND E-TFR ***Z", account="chq", kind="depository",
                              who="Sam"))
    imp = client.post("/api/transfers/sort", json={
        "ids": [ids["SEND E-TFR ***Z"]], "category": category}).get_json()["impact"]
    assert imp["delta"] >= 0, imp


def test_undo_refuses_what_it_did_not_make(client):
    ids = load(client.st, row(10, "COFFEE", category="Coffee"))
    bad = [
        {"rows": [{"id": "nope", "category": "Dining", "source": "user"}]},
        {"rows": [{"id": ids["COFFEE"], "category": "Not a category", "source": "user"}]},
        {"rows": [{"id": ids["COFFEE"], "category": "Dining", "source": "x; DROP"}]},
        {"overrides": {"coffee": "Nope"}},
        {"rows": "everything"},
    ]
    for body in bad:
        assert client.post("/api/transactions/undo", json=body).status_code == 400, body
    assert cat(client.st, ids["COFFEE"]) == "Coffee"


# ── Skipped (THL-213) ────────────────────────────────────────────────────

def test_skipped_stays_skipped_and_leaves_the_badge(client):
    load(client.st, row(40, "SEND E-TFR ***Ab1", account="chq", kind="depository"),
         row(25, "MYSTERY SHOP", merchant="Mystery Shop"))
    before = client.get("/api/review").get_json()
    assert before["count"] == 2 and before["skipped"] == 0
    key = "u:" + before["unsorted"]["transfers"][0]["id"]
    assert client.post("/api/review/skip", json={"key": key}).status_code == 200
    after = client.get("/api/review").get_json()
    assert after["count"] == 1 and after["skipped"] == 1
    assert after["unsorted"]["transfers"][0]["skipped"] is True        # still listed
    assert client.get("/api/home").get_json()["review_count"] == 1
    # Back to the queue.
    client.post("/api/review/skip", json={"key": key, "skip": False})
    again = client.get("/api/review").get_json()
    assert again["count"] == 2 and again["skipped"] == 0


def test_skipping_needs_an_item(client):
    assert client.post("/api/review/skip", json={}).status_code == 400
