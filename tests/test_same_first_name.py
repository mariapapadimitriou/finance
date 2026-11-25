"""Two people with one first name (product owner, 2026-11-25): a payback from
Georgia Klev showed as Georgia Pappas's, and Georgia Pappas's money linked to
Georgia Klev's split was recorded as Klev's. Demo data only."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import splits as sp
from finance.etransfers import person_for
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
KLEV, PAPPAS = "Georgia Klev", "Georgia Pappas"


def tx(desc, amount, ago, account="chq", kind="depository", when=None):
    return Transaction(date=when or (TODAY - timedelta(days=ago)).isoformat(), description=desc, amount=amount,
                       account_id=account, account_name=account,
                       raw={"account_type": kind, "issuer_category":
                            "TRANSFER_IN_ACCOUNT_TRANSFER" if amount < 0 else "FOOD_AND_DRINK_RESTAURANT"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "g.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


WORDS = {"e-transfer": ("E-TRANSFER FROM GEORGIA KLEV", "E-TRANSFER FROM GEORGIA PAPPAS"),
         "handle": ("Cash Received - georgiaklev", "Cash Received - georgiapappas")}


def two_splits(c, words="e-transfer", first=KLEV):
    """A dinner split with each Georgia, and $40 and $30 from them."""
    k, p = WORDS[words]
    # The order the people are met in mustn't decide who anyone is.
    ago = (9, 8) if first == KLEV else (8, 9)
    ingest(c.st, IngestResult([tx("DINNER ONE", 80, ago[0], "card", "credit"),
                               tx("DINNER TWO", 60, ago[1], "card", "credit")], "card"))
    ingest(c.st, IngestResult([tx(k, -40, 5), tx(p, -30, 4)], "chq"))
    by = {t.description: t.fingerprint for t in c.st.all_transactions()}
    order = [("DINNER ONE", KLEV), ("DINNER TWO", PAPPAS)]
    for d, n in order if first == KLEV else order[::-1]:
        assert c.put(f"/api/transactions/{by[d]}/split",
                     json={"mode": "even", "people": [{"name": n}]}).status_code == 200
    return by["DINNER ONE"], by["DINNER TWO"], by[k], by[p]


def pay(c, deposit, charge, person=None):
    body = {"case": "payback", "charge": charge, **({"person": person} if person else {})}
    return c.post(f"/api/transactions/{deposit}/mark", json=body)


def paid(c, charge):
    people = c.get(f"/api/transactions/{charge}").get_json()["splitting"]["people"]
    return {p["name"]: p["paid"] for p in people}


def shown(c, txn):
    return c.get(f"/api/transactions/{txn}").get_json()["merchant"]


@pytest.mark.parametrize("first", [KLEV, PAPPAS])
@pytest.mark.parametrize("words", WORDS)
def test_each_payback_shows_who_sent_it(client, words, first):
    one, two, k, p = two_splits(client, words, first)
    assert pay(client, p, two).status_code == 200 and pay(client, k, one).status_code == 200
    assert (shown(client, k), shown(client, p)) == (KLEV, PAPPAS)
    assert client.st.payback_people() == {k: KLEV, p: PAPPAS}
    assert paid(client, one) == {KLEV: 40.0} and paid(client, two) == {PAPPAS: 30.0}


@pytest.mark.parametrize("person", [None, PAPPAS])
@pytest.mark.parametrize("words", WORDS)
def test_one_georgia_is_never_credited_for_the_other(client, words, person):
    one, two, k, p = two_splits(client, words)
    r = pay(client, p, one, person)
    # Not clear who on this split paid: it asks, and nothing is saved.
    assert r.status_code == 409 and r.get_json()["who_paid"]["sender"] == PAPPAS
    assert client.st.payback_people() == {} and paid(client, one) == {KLEV: 0.0}
    # Her own answer stands: Klev paid with Pappas's account.
    assert pay(client, p, one, KLEV).status_code == 200
    assert paid(client, one) == {KLEV: 30.0}


def test_owed_to_you_keeps_them_apart(client):
    two_splits(client)
    rows = client.get("/api/owed").get_json()["owes_you"]
    assert {r["name"]: r["total"] for r in rows} == {KLEV: 40.0, PAPPAS: 30.0}


def test_needs_a_look_suggests_the_right_one(client):
    one, two, k, p = two_splits(client)
    for deposit, charge, name in ((k, one, KLEV), (p, two, PAPPAS)):
        s = client.get(f"/api/transactions/{deposit}").get_json()["repayment"]["suggestion"]
        assert (s["charge_id"], s["name"]) == (charge, name)


@pytest.mark.parametrize("a,b,same", [
    (KLEV, PAPPAS, False), ("Georgia", KLEV, True), ("Georgia K", KLEV, True), ("Georgia K.", PAPPAS, False),
    ("Priya S", "Priya Shah", True), ("georgiaklev", PAPPAS, False), ("georgiaklev", KLEV, True),
    ("Anastasiapapas", "Anastasia Papadimitriou", True), ("Georgia M Klev", KLEV, True), ("SAM LEE 123", "Sam Lee", True),
])
def test_same_person(a, b, same):
    assert sp.same_person(a, b) is same and sp.same_person(b, a) is same


def test_pick():
    assert sp.pick([KLEV, PAPPAS], PAPPAS) == PAPPAS
    assert sp.pick(["Georgia", KLEV], KLEV) == KLEV
    assert sp.pick([KLEV, PAPPAS], "Georgia") is None
    assert sp.pick(["Georgia"], KLEV) == "Georgia"


@pytest.mark.parametrize("tag,people,who", [
    ("georgiaklev", [PAPPAS, KLEV], KLEV), ("georgiaklev", [KLEV, PAPPAS], KLEV), ("georgiaklev", [PAPPAS], None),
    ("georgia", [PAPPAS, KLEV], None), ("georgiak", [PAPPAS, KLEV], KLEV), ("georgia", [KLEV], KLEV),
    ("anastasiapapas", ["Anastasia Papadimitriou"], "Anastasia Papadimitriou"),
])
def test_a_handle_names_one_person_or_nobody(tag, people, who):
    assert person_for(tag, people) == who


def test_a_payback_already_linked_is_read_as_it_was(client):
    """One dated before 2026-11-25 keeps its credit: nothing she has already
    seen settled comes undone."""
    ingest(client.st, IngestResult([tx("DINNER", 80, 0, "card", "credit", when="2026-11-01")], "card"))
    ingest(client.st, IngestResult([tx("E-TRANSFER FROM GEORGIA PAPPAS", -40, 0, when="2026-11-05")], "chq"))
    by = {t.description: t.fingerprint for t in client.st.all_transactions()}
    client.put(f"/api/transactions/{by['DINNER']}/split", json={"mode": "even", "people": [{"name": KLEV}]})
    client.st.link_payback(by["DINNER"], by["E-TRANSFER FROM GEORGIA PAPPAS"], PAPPAS, None)
    assert paid(client, by["DINNER"]) == {KLEV: 40.0}


def test_the_app_says_the_same(tmp_path):
    """JointSplitViews.samePerson, run: it hid Georgia Klev from her contacts
    because Georgia Pappas was in her recent splits."""
    import json
    import shutil
    import subprocess
    from pathlib import Path
    if shutil.which("swiftc") is None:
        pytest.skip("no Swift compiler here")
    src = (Path(__file__).resolve().parents[1] / "ios" / "Pearl" / "Views" / "Transactions"
           / "JointSplitViews.swift").read_text()
    func = "func samePerson" + src.split("func samePerson", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
    names = ["Georgia", KLEV, PAPPAS, "Georgia K.", "Georgia M Klev", "Priya S", "Priya Shah", "SAM LEE 123",
             "Sam Lee", "Sam", "Anastasia Papas", "Anastasia Papadimitriou", "Siobhan O'Neil", "Siobhan ONeil", ""]
    pairs = [(a, b) for a in names for b in names]
    main = tmp_path / "main.swift"
    main.write_text("import Foundation\n" + func + "let pairs: [[String]] = " + json.dumps([list(p) for p in pairs])
                    + "\nprint(pairs.map { samePerson($0[0], $0[1]) ? \"1\" : \"0\" }.joined())\n")
    exe = tmp_path / "same"
    subprocess.run(["swiftc", str(main), "-o", str(exe)], check=True, capture_output=True, timeout=240)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=60).stdout.strip()
    differ = [p for p, got in zip(pairs, out) if (got == "1") != sp.same_person(*p)]
    assert differ == []


def test_both_georgias_on_one_split(client):
    ingest(client.st, IngestResult([tx("DINNER", 90, 5, "card", "credit")], "card"))
    ingest(client.st, IngestResult([tx(WORDS["e-transfer"][0], -30, 3), tx(WORDS["e-transfer"][1], -25, 2)], "chq"))
    by = {t.description: t.fingerprint for t in client.st.all_transactions()}
    assert client.put(f"/api/transactions/{by['DINNER']}/split",
                      json={"mode": "even", "people": [{"name": KLEV}, {"name": PAPPAS}]}).status_code == 200
    for d in WORDS["e-transfer"]:
        assert pay(client, by[d], by["DINNER"]).status_code == 200
    assert paid(client, by["DINNER"]) == {KLEV: 30.0, PAPPAS: 25.0}
    assert client.post(f"/api/transactions/{by['DINNER']}/split/let-go", json={"name": PAPPAS}).status_code == 200
    people = client.get(f"/api/transactions/{by['DINNER']}").get_json()["splitting"]["people"]
    assert {p["name"]: p["amount"] for p in people} == {KLEV: 30.0, PAPPAS: 25.0}
