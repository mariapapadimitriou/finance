"""P5 (fewer taps, TP-P5-FromPurchase): Which money paid this back? lists
the finder's likely money first, then recent money in, never "No money in
matches" while anything came in. Listing links nothing."""
from finance.ingest.base import IngestResult
from finance.pipeline import ingest

import sys
sys.path.insert(0, "tests")
from test_fewer_taps_server import ago, ids, row  # noqa: E402
from test_fewer_taps_server import client  # noqa: E402,F401


def test_recent_money_in_follows_the_likely_list(client):
    from test_splits import etransfer_in
    ingest(client.st, IngestResult(transactions=[row(127.5, "TST* GUSTO 504", ago(6))], account_id="card"))
    ingest(client.st, IngestResult(transactions=[
        etransfer_in(42.5, "Priya Shah", ago(2)),
        row(-60, "INTERAC E-TRANSFER", ago(3), account="chq", kind="depository"),
        row(-900, "PAYROLL", ago(1), account="chq", kind="depository")], account_id="chq"))
    i = ids(client.st)
    tid = i["TST* GUSTO 504"]
    find = client.get(f"/api/transactions/{tid}/paid-back-find").get_json()
    body = client.get(f"/api/transactions/{tid}/paid-back-recent").get_json()
    got = [c["id"] for c in body["candidates"]]
    # The finder's own order first, unchanged.
    assert got[:len(find["candidates"])] == [c["id"] for c in find["candidates"]]
    assert got[0] == i["E-TRANSFER RECEIVED PRIYA SHAH"]
    # Money the finder didn't call likely is still there to pick.
    assert i["INTERAC E-TRANSFER"] in got
    assert body["left"] == find["left"] and body["merchant"] == find["merchant"]
    # Nothing was linked by listing it.
    assert not client.st.parts() and client.st.get_transaction(tid).paid_back in (None, 0, 0.0)


def test_a_search_is_the_finders_own(client):
    ingest(client.st, IngestResult(transactions=[row(30, "NOODLE BAR", ago(5))], account_id="card"))
    ingest(client.st, IngestResult(transactions=[row(-12, "INTERAC E-TRANSFER", ago(2), account="chq",
                                                     kind="depository")], account_id="chq"))
    tid = ids(client.st)["NOODLE BAR"]
    a = client.get(f"/api/transactions/{tid}/paid-back-recent?q=12").get_json()
    b = client.get(f"/api/transactions/{tid}/paid-back-find?q=12").get_json()
    assert [c["id"] for c in a["candidates"]][:len(b["candidates"])] == [c["id"] for c in b["candidates"]]


def test_a_payback_from_a_clear_name_on_an_unsplit_purchase_is_their_share(client):
    """Owner point 7: the split made by paybacks, their share what they paid."""
    from test_splits import etransfer_in
    ingest(client.st, IngestResult(transactions=[row(127.5, "TST* GUSTO 504", ago(4))], account_id="card"))
    ingest(client.st, IngestResult(transactions=[etransfer_in(42.5, "Priya Shah", ago(1))], account_id="chq"))
    i = ids(client.st)
    purchase, money = i["TST* GUSTO 504"], i["E-TRANSFER RECEIVED PRIYA SHAH"]
    r = client.post(f"/api/transactions/{money}/parts", json={"parts": [
        {"kind": "payback", "charge": purchase, "amount": 42.5, "person": "Priya Shah", "new_split": True}]})
    assert r.status_code == 200, r.get_json()
    split = client.st.splits()[purchase]
    priya = next(p for p in split["people"] if p["name"] == "Priya Shah")
    assert round(priya.get("amount", priya.get("share", 0)), 2) == 42.5
    assert client.st.get_transaction(purchase).my_share == 85.0
    # One Undo takes the payback and the split it made.
    assert client.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
    assert purchase not in client.st.splits()
