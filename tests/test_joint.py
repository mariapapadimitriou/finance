"""Joint accounts: spending on one is hers by default, or her set share of
every purchase; money in counts once she says whose it was, and what the
others put in doesn't shrink her share by itself (2026-10-23)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


def day(n):
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(amount, description, account, category=None):
    return Transaction(date=day(1), description=description, amount=amount,
                       account_id=account, account_name=account,
                       raw={"account_type": "depository"}, category=category)


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "joint.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = c.application.config["STORE"]
        ingest(st, IngestResult([row(120, "LOBLAWS", "fam"),
                                 row(-1000, "PAYROLL DEPOSIT DAD", "fam"),
                                 row(-500, "TFR-FR 1111111", "fam"),
                                 row(80, "SEND E-TFR ***Mom1", "fam")], "fam"))
        ingest(st, IngestResult([row(500, "TFR-TO 2222222", "chq")], "chq"))
        c.put("/api/accounts/fam/joint", json={"label": "Family"})
        yield c


def month(c):
    return next(m for m in c.get("/api/summary").get_json()["monthly"] if m["month"] == MONTH)


def ids(c):
    return {t["description"]: t["id"] for t in c.get("/api/transactions").get_json()["transactions"]}


def test_mine_by_default(client):
    m = month(client)
    # Loblaws, and the e-transfer out until it's sorted.
    assert m["spend"] == 200
    assert m["income"] == 0 and m["inflows"] == 0  # money in waits for an answer
    accounts = {a["account_id"]: a for a in client.get("/api/accounts").get_json()["accounts"]}
    assert accounts["fam"]["joint"] == "Family"


def test_mine_and_part(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 0})
    assert month(client)["spend"] == 80           # this one's theirs
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 40})
    assert month(client)["spend"] == 120
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": None})
    assert month(client)["spend"] == 200


def test_a_deposit_can_be_mine_too(client):
    i = ids(client)
    r = client.put(f"/api/transactions/{i['PAYROLL DEPOSIT DAD']}/share",
                   json={"my_share": -1000})
    assert r.status_code == 200
    assert month(client)["income"] == 1000


def test_always_mine_at_a_name(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/mine-always", json={"on": True})
    st = client.application.config["STORE"]
    ingest(st, IngestResult([row(30, "LOBLAWS", "fam"),
                             row(-75, "E-TRANSFER FROM SISTER", "fam")], "fam"))
    sister = ids(client)["E-TRANSFER FROM SISTER"]
    client.put(f"/api/transactions/{sister}/joint-from", json={"who": "them"})
    # Every purchase is hers until she marks it (2026-10-23): her sister's
    # $75 is "Joint added" and changes nothing of hers.
    assert month(client)["spend"] == 120 + 30 + 80


def test_your_transfer_into_it_is_matched(client):
    rows = {t["description"]: t for t in client.get("/api/transactions").get_json()["transactions"]}
    assert rows["TFR-TO 2222222"]["category"] == "Transfers"


def test_her_transfer_out_of_it_is_hers_to_sort(client):
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 1


def test_unmarking_restores_normal_counting(client):
    client.put("/api/accounts/fam/joint", json={"label": None})
    # Loblaws, and the e-transfer out, which is waiting to be sorted again.
    assert month(client)["spend"] == 200
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 1


@pytest.mark.parametrize("share", [200, -50, "lots"])
def test_bad_shares_are_refused(client, share):
    i = ids(client)
    assert client.put(f"/api/transactions/{i['LOBLAWS']}/share",
                      json={"my_share": share}).status_code == 400


# ── Who put money in: hers, or theirs ("Joint added", 2026-10-23) ──────

def sister_in(client, amount, ref="1"):
    st = client.application.config["STORE"]
    t = row(-amount, f"E-TRANSFER {ref} FROM SISTER", "fam")
    t.merchant = "Sister"
    ingest(st, IngestResult([t], "fam"))
    return ids(client)[f"E-TRANSFER {ref} FROM SISTER"]


def answer(client, tid, who, remember=False):
    return client.put(f"/api/transactions/{tid}/joint-from",
                      json={"who": who, "remember": remember})


def test_her_sisters_deposit_is_joint_added_and_changes_nothing_of_hers(client):
    tid = sister_in(client, 60)
    assert answer(client, tid, "them").status_code == 200
    # Her purchases are hers until she marks them; the $60 isn't hers.
    assert month(client)["spend"] == 200
    assert month(client)["income"] == 0


def test_a_big_deposit_from_them_still_leaves_her_spending_as_it_was(client):
    answer(client, sister_in(client, 500), "them")
    assert month(client)["spend"] == 200


def test_her_own_money_in_is_a_transfer_not_income(client):
    i = ids(client)
    r = answer(client, i["PAYROLL DEPOSIT DAD"], "me")
    assert r.status_code == 200
    m = month(client)
    assert m["income"] == 0 and m["spend"] == 200
    row_ = next(t for t in client.get("/api/transactions").get_json()["transactions"]
                if t["id"] == i["PAYROLL DEPOSIT DAD"])
    assert row_["category"] == "Transfers"


def test_remembered_for_that_sender(client):
    answer(client, sister_in(client, 30), "them", remember=True)
    second = sister_in(client, 30, ref="2")
    # Same sender, so both are theirs, and the second isn't asked about.
    asked = {q["txn"]["id"] for q in client.get("/api/review").get_json()["joint_in"]}
    assert second not in asked
    assert month(client)["spend"] == 200


def test_asking_again_and_bad_answers(client):
    tid = sister_in(client, 60)
    answer(client, tid, "them")
    assert answer(client, tid, None).status_code == 200
    assert month(client)["spend"] == 200
    assert answer(client, tid, "dad").status_code == 400
    assert answer(client, ids(client)["LOBLAWS"], "them").status_code == 400   # not money in


def test_needs_a_look_asks_who_put_it_in(client):
    review = client.get("/api/review").get_json()
    asked = {q["txn"]["description"] for q in review["joint_in"]}
    assert asked == {"PAYROLL DEPOSIT DAD"}       # the TFR-FR is her own, matched
    assert review["joint_in"][0]["label"] == "Family"
    answer(client, ids(client)["PAYROLL DEPOSIT DAD"], "them")
    assert client.get("/api/review").get_json()["joint_in"] == []


def test_a_set_share_still_wins(client):
    client.put("/api/accounts/fam/settings", json={"joint_share": 50})
    answer(client, sister_in(client, 60), "them")
    assert month(client)["spend"] == 100            # half of everything, as she set


# ── Who it's shared with (2026-10-14) ────────────────────────────────────

def test_she_names_who_she_shares_it_with(client):
    r = client.put("/api/accounts/fam/settings", json={"joint_people": ["Sam", " alex ", "Sam"]})
    assert r.status_code == 200
    a = r.get_json()["account"]
    assert a["joint_people"] == ["Sam", "alex"]
    accounts = {x["account_id"]: x for x in client.get("/api/accounts").get_json()["accounts"]}
    assert accounts["fam"]["joint"] == "Sam and alex"          # the label follows the names
    assert client.put("/api/accounts/fam/settings",
                      json={"joint_people": ["  "]}).status_code == 400


def test_who_put_it_in_is_one_of_them(client):
    client.put("/api/accounts/fam/settings", json={"joint_people": ["Sam", "Alex"]})
    tid = sister_in(client, 60)
    q = next(q for q in client.get("/api/review").get_json()["joint_in"] if q["txn"]["id"] == tid)
    assert q["people"] == ["Sam", "Alex"]
    r = client.put(f"/api/transactions/{tid}/joint-from",
                   json={"who": "them", "person": "Alex", "remember": True})
    assert r.status_code == 200 and r.get_json()["person"] == "Alex"
    listed = next(t for t in client.get("/api/transactions/list",
                                        query_string={"month": MONTH, "joint": "1"}).get_json()["transactions"]
                  if t["id"] == tid)
    assert listed["joint_person"] == "Alex"
    assert listed["note"].startswith("Alex put this in")
    assert listed["chip"]["label"] == "Joint added"
    # Theirs, and her spending is as it was (2026-10-23).
    assert month(client)["spend"] == 200
    # The next deposit from that sender is remembered as Alex's too.
    tid2 = sister_in(client, 10, ref="2")
    t2 = next(t for t in client.get("/api/transactions/list",
                                    query_string={"month": MONTH, "joint": "1"}).get_json()["transactions"]
              if t["id"] == tid2)
    assert t2["joint_person"] == "Alex"


def test_only_someone_she_named(client):
    client.put("/api/accounts/fam/settings", json={"joint_people": ["Sam"]})
    tid = sister_in(client, 60)
    assert client.put(f"/api/transactions/{tid}/joint-from",
                      json={"who": "them", "person": "Jo"}).status_code == 400
    assert client.put(f"/api/transactions/{tid}/joint-from",
                      json={"who": "me", "person": "Sam"}).status_code == 400


def test_transfers_is_called_transfers(client):
    rows = client.get("/api/transactions/list", query_string={"month": MONTH}).get_json()
    notes = {t["note"] for t in rows["transactions"]}
    assert not any("Between your accounts" in (n or "") for n in notes)


def test_split_account_splits_purchases_but_never_a_deposit(client):
    """2026-10-23: with her sister every purchase is 50/50, but they each put
    money in separately, so a deposit is hers only when she says so."""
    client.put("/api/accounts/fam/settings", json={"joint_share": 50})
    i = ids(client)
    assert month(client)["spend"] == 100                      # half of Loblaws and the e-transfer out
    sis = sister_in(client, 60)
    st = client.application.config["STORE"]
    assert st.get_transaction(sis).my_share == 0              # not half hers: asked
    asked = {q["txn"]["id"] for q in client.get("/api/review").get_json()["joint_in"]}
    assert sis in asked
    answer(client, sis, "them")
    rows = {r["id"]: r for r in client.get("/api/transactions/list",
                                           query_string={"month": MONTH, "joint": "1"}).get_json()["transactions"]}
    assert rows[sis]["chip"]["label"] == "Joint added"
    # Her own money in is a transfer, never Saved, and all hers.
    st.set_transaction_category(i["PAYROLL DEPOSIT DAD"], "Saved")
    answer(client, i["PAYROLL DEPOSIT DAD"], "me")
    mine = st.get_transaction(i["PAYROLL DEPOSIT DAD"])
    assert mine.category == "Transfers" and mine.my_share == mine.amount
    assert month(client)["spend"] == 100


def test_a_purchase_marked_theirs_is_joint_spent(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 0})
    rows = {r["id"]: r for r in client.get("/api/transactions/list",
                                           query_string={"month": MONTH, "joint": "1"}).get_json()["transactions"]}
    assert rows[i["LOBLAWS"]]["chip"]["label"] == "Joint spent"
    assert rows[i["LOBLAWS"]]["note"] == "Family’s · not your spending"


def test_split_once_split_always(client):
    """Part of one charge on a joint account splits every charge from that
    name there the same way, old and new, until she says otherwise
    (2026-10-26)."""
    st = client.application.config["STORE"]
    ingest(st, IngestResult([row(60, "LOBLAWS", "fam"), row(50, "LOBLAWS", "chq")], "fam"))
    i = {t.description + str(t.amount): t.fingerprint for t in st.all_transactions()}
    r = client.put(f"/api/transactions/{i['LOBLAWS120.0']}/share", json={"my_share": 60}).get_json()
    assert r["rule"] == ("Every Loblaws charge on this joint account is split this way "
                         "from now on: 50% yours.")
    by = {(t.account_id, t.amount): t for t in st.all_transactions() if t.description == "LOBLAWS"}
    assert by[("fam", 60.0)].my_share == 30.0 and not by[("fam", 60.0)].share_set
    assert by[("chq", 50.0)].my_share is None          # only on that joint account
    # A new one arrives already split.
    ingest(st, IngestResult([row(90, "LOBLAWS", "fam")], "fam"))
    new = next(t for t in st.all_transactions() if t.amount == 90)
    assert new.my_share == 45.0 and new.joint_split == 50.0
    listed = {t["id"]: t for t in client.get("/api/transactions/list?limit=50").get_json()["transactions"]}
    assert listed[new.fingerprint]["joint_split"] == 50.0
    # "Mine" on one of them is that one only; the rest stay split.
    client.put(f"/api/transactions/{new.fingerprint}/share", json={"my_share": None})
    assert st.get_transaction(new.fingerprint).my_share == 90.0
    assert st.get_transaction(by[("fam", 60.0)].fingerprint).my_share == 30.0
    # Unticking "Always split" stops it.
    client.put(f"/api/transactions/{by[('fam', 60.0)].fingerprint}/share",
               json={"my_share": 20, "always": False})
    ingest(st, IngestResult([row(10, "LOBLAWS", "fam")], "fam"))
    assert next(t for t in st.all_transactions() if t.amount == 10).my_share == 10.0


def test_always_mine_ends_always_split(client):
    st = client.application.config["STORE"]
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 30})
    assert st.get_transaction(i["LOBLAWS"]).joint_split == 25.0
    client.put(f"/api/transactions/{i['LOBLAWS']}/mine-always", json={"on": True})
    ingest(st, IngestResult([row(40, "LOBLAWS", "fam")], "fam"))
    assert next(t for t in st.all_transactions() if t.amount == 40).my_share == 40.0


class TestChangingHowPurchasesCount:
    """2026-10-26: her sister set 50% after sorting a lot of purchases. The
    change can apply to every purchase on the account, or from today on."""

    def setup(self, client):
        st = client.application.config["STORE"]
        old = Transaction(date=(TODAY - timedelta(days=40)).isoformat(), description="COSTCO",
                          amount=200, account_id="fam", account_name="fam",
                          raw={"account_type": "depository"}, category="Groceries")
        ingest(st, IngestResult([old], "fam"))
        new = Transaction(date=TODAY.isoformat(), description="SHELL", amount=60, account_id="fam",
                          account_name="fam", raw={"account_type": "depository"}, category="Gas")
        ingest(st, IngestResult([new], "fam"))
        by = {t.description: t.fingerprint for t in st.all_transactions()}
        return st, by

    def share(self, st, by, name):
        return st.get_transaction(by[name]).my_share

    def test_every_purchase_including_sorted_ones(self, client):
        st, by = self.setup(client)
        # Sorted earlier: one said "Mine" outright, one someone else's.
        client.put(f"/api/transactions/{by['LOBLAWS']}/share", json={"my_share": 120})
        client.put(f"/api/transactions/{by['SEND E-TFR ***Mom1']}/share", json={"my_share": 0})
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 50, "apply": "all"})
        assert r.status_code == 200 and r.get_json()["applied"]["cleared"] == 1
        assert self.share(st, by, "LOBLAWS") == 60
        assert self.share(st, by, "COSTCO") == 100 and self.share(st, by, "SHELL") == 30
        assert self.share(st, by, "SEND E-TFR ***Mom1") == 0        # her answer stays

    def test_from_today_leaves_earlier_purchases_as_they_were(self, client):
        st, by = self.setup(client)
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 50, "apply": "from_today"})
        assert r.get_json()["applied"]["kept"] >= 1
        assert self.share(st, by, "COSTCO") == 200
        assert self.share(st, by, "SHELL") == 30
        # Changing it again "every purchase" moves the held ones too.
        client.put("/api/accounts/fam/settings", json={"joint_share": 40, "apply": "all"})
        assert self.share(st, by, "COSTCO") == 80 and self.share(st, by, "SHELL") == 24
        # And back to all mine, from today: earlier ones keep 40%.
        client.put("/api/accounts/fam/settings", json={"joint_share": "auto", "apply": "from_today"})
        assert self.share(st, by, "COSTCO") == 80 and self.share(st, by, "SHELL") == 60

    def test_a_bad_choice_or_share_changes_nothing(self, client):
        st, by = self.setup(client)
        assert client.put("/api/accounts/fam/settings",
                          json={"joint_share": 50, "apply": "sometimes"}).status_code == 400
        assert client.put("/api/accounts/fam/settings",
                          json={"joint_share": 150, "apply": "from_today"}).status_code == 400
        assert self.share(st, by, "COSTCO") == 200 and not st.get_transaction(by["COSTCO"]).share_set
