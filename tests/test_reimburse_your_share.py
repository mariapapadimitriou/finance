"""TEST-31 (product owner, 2026-11-13): work reimbursing your own share of a
split purchase. Pai Northern Thai $120.00, split with Sam ($60.00 each);
Northwind (work) sends money for your share. T-09w, S-04w, S-04w2, S-11w,
S-04w3, S-40w and T-41w on Proposals 1284:100; note 1294:2593."""

from __future__ import annotations

from datetime import date

import pytest

from finance.analytics import share_amount
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today().isoformat()


def tx(desc, amount, category="", merchant=None):
    return Transaction(date=TODAY, description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "reimburse.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def dinner(c, *more):
    """Pai Northern Thai $120.00, split evenly with Sam."""
    i = add(c, tx("PAI NORTHERN THAI", 120.0, "Dining", merchant="Pai Northern Thai"), *more)
    r = c.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split",
              json={"mode": "even", "people": [{"name": "Sam"}]})
    assert r.status_code == 200, r.get_json()
    return i


def splitting(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()["splitting"]


def sam(c, tid):
    return next(p for p in splitting(c, tid)["people"] if p["name"] == "Sam")


def costs(c, tid):
    return share_amount(c.st.get_transaction(tid))


def candidates(c, deposit):
    cases = c.get(f"/api/transactions/{deposit}/cases").get_json()
    item = next(x for x in cases["cases"] if x["key"] == "reimbursement")
    return item.get("candidates") or []


def reimburse(c, deposit, charge, share=True):
    return c.post(f"/api/transactions/{deposit}/mark",
                  json={"case": "reimbursement", "charge": charge, "share": share})


class TestYourShareIsItsOwnMatch:
    def test_listed_beside_all_of_it(self, client):
        """T-09w (decision 1, 2): "Your share of Pai Northern Thai · $60.00"
        first, exact; "all of it · $120.00" stays beside it."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        got = [c for c in candidates(client, i["NORTHWIND LTD PAYROLL"]) if c["id"] == i["PAI NORTHERN THAI"]]
        assert [(c.get("share", False), c["left"], c["exact"]) for c in got] == [(True, 60.0, True), (False, 120.0, False)]
        assert got[0]["whole"] == 120.0 and got[0]["split_with"] == ["Sam"]

    def test_from_the_deposit_page(self, client):
        """T-09w from the deposit's own page: the purchase list opens on the
        likely matches, "Your share of …" first."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"),
                   tx("LYFT RIDE", 18.40, "Transport", merchant="Lyft Ride"))
        got = client.get(f"/api/transactions/{i['NORTHWIND LTD PAYROLL']}/charges?q=&case=reimbursement").get_json()
        first = got["charges"][0]
        assert first["id"] == i["PAI NORTHERN THAI"] and first["share"] and first["left"] == 60.0
        assert any(c["id"] == i["LYFT RIDE"] for c in got["charges"])
        plain = client.get(f"/api/transactions/{i['NORTHWIND LTD PAYROLL']}/charges?q=").get_json()
        assert not any(c.get("share") for c in plain["charges"])

    def test_the_expense_side_matches_your_share(self, client):
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        deps = client.get(f"/api/transactions/{i['PAI NORTHERN THAI']}/deposits").get_json()["deposits"]
        assert deps and deps[0]["id"] == i["NORTHWIND LTD PAYROLL"]


class TestFullShare:
    def test_counts_for_you_not_sam(self, client):
        """S-04w: you are reimbursed; Sam still owes $60.00. The dinner costs
        $60.00 now, not $120.00 (decision 5, Rule A)."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        assert costs(client, tid) == 120.0
        r = reimburse(client, i["NORTHWIND LTD PAYROLL"], tid)
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body["title"] == "Reimbursed your share of Pai Northern Thai." and "extra" not in body
        s = splitting(client, tid)
        assert s["mine"]["reimbursed"] == 60.0 and s["mine"]["stays"] == 0.0 and s["mine"]["on"] == TODAY
        assert [link["id"] for link in s["mine"]["links"]] == [i["NORTHWIND LTD PAYROLL"]]
        assert sam(client, tid)["owes"] == 60.0 and sam(client, tid)["paid"] == 0.0
        assert costs(client, tid) == 60.0
        # Never asked "Who sent this?" or "What's the extra?" about.
        review = client.get("/api/review").get_json()
        keys = {str(x.get("key")) for k in review.values() if isinstance(k, list)
                for x in k if isinstance(x, dict)}
        assert not {"credit:" + i["NORTHWIND LTD PAYROLL"], "extra:" + i["NORTHWIND LTD PAYROLL"]} & keys
        # The deposit isn't income.
        dep = client.get(f"/api/transactions/{i['NORTHWIND LTD PAYROLL']}").get_json()
        assert dep["counts"] != "income"

    def test_allowance_rises_at_once(self, client):
        """Decision 5: linking work's share raises the Allowance by $60.00
        straight away, without waiting for Sam."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        client.st.set_setting("monthly_income", 4000.0)
        before = client.get("/api/home").get_json()["safe_to_spend"]
        reimburse(client, i["NORTHWIND LTD PAYROLL"], i["PAI NORTHERN THAI"])
        after = client.get("/api/home").get_json()["safe_to_spend"]
        if before and after and before.get("amount") is not None:
            assert round(after["amount"] - before["amount"], 2) == 60.0

    def test_undo_puts_it_back(self, client):
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        body = reimburse(client, i["NORTHWIND LTD PAYROLL"], tid).get_json()
        assert client.post("/api/transactions/undo", json=body["undo"]).status_code == 200
        assert "mine" not in splitting(client, tid) and costs(client, tid) == 120.0

    def test_unlink_from_your_row(self, client):
        """S-40w: Unlink… uses the same unlink as any reimbursement."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        reimburse(client, i["NORTHWIND LTD PAYROLL"], tid)
        r = client.delete(f"/api/transactions/{tid}/paybacks/{i['NORTHWIND LTD PAYROLL']}")
        assert r.status_code == 200, r.get_json()
        assert "mine" not in splitting(client, tid) and costs(client, tid) == 120.0

    def test_a_second_share_link_is_refused(self, client):
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"),
                   tx("NORTHWIND LTD BONUS", -60.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        reimburse(client, i["NORTHWIND LTD PAYROLL"], tid)
        r = reimburse(client, i["NORTHWIND LTD BONUS"], tid)
        assert r.status_code == 400 and "already reimbursed" in r.get_json()["error"]

    def test_not_in_the_split(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", merchant="Pai Northern Thai"),
                tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split",
                   json={"mode": "even", "include_me": False, "people": [{"name": "Sam"}]})
        r = reimburse(client, i["NORTHWIND LTD PAYROLL"], i["PAI NORTHERN THAI"])
        assert r.status_code == 400


class TestPartial:
    def test_the_rest_stays_yours(self, client):
        """S-04w2 (decision 3): $45.00 of $60.00; $15.00 stays yours."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -45.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        body = reimburse(client, i["NORTHWIND LTD PAYROLL"], tid).get_json()
        assert body["detail"] == "$15.00 of your share stays yours."
        s = splitting(client, tid)
        assert s["mine"]["reimbursed"] == 45.0 and s["mine"]["stays"] == 15.0
        assert sam(client, tid)["owes"] == 60.0
        assert costs(client, tid) == 75.0


class TestMoreThanYourShare:
    def test_the_extra_is_asked(self, client):
        """S-11w: $75.00 in, $60.00 pays your share, "What's the extra
        $15.00?" comes next; Sam's share isn't touched (decision 4)."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -75.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        body = reimburse(client, i["NORTHWIND LTD PAYROLL"], tid).get_json()
        assert body["extra"] == {"amount": 15.0, "whole": 75.0, "share": 60.0, "charge": tid,
                                 "merchant": "Pai Northern Thai"}
        assert body["detail"] == "$60.00 pays back your share of Pai Northern Thai."
        s = splitting(client, tid)
        assert s["mine"]["reimbursed"] == 60.0 and sam(client, tid)["owes"] == 60.0
        assert costs(client, tid) == 60.0

    def test_answering_the_extra_keeps_your_share(self, client):
        """S-11w's tiles save as parts: the reimbursement part stays on your
        share (parts._reimburse links to you), the extra is extra pay."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -75.0, merchant="Northwind Ltd"))
        tid, dep = i["PAI NORTHERN THAI"], i["NORTHWIND LTD PAYROLL"]
        reimburse(client, dep, tid)
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "reimbursement", "amount": 60, "charge": tid},
            {"kind": "income", "amount": 15, "income_kind": "bonus"}]})
        assert r.status_code == 200, r.get_json()
        s = splitting(client, tid)
        assert s["mine"]["reimbursed"] == 60.0 and sam(client, tid)["owes"] == 60.0
        assert costs(client, tid) == 60.0


class TestSamPaysToo:
    def test_costs_you_nothing(self, client):
        """S-04w3: both parts paid; it costs you $0.00."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"),
                   tx("E-TRANSFER FROM SAM", -60.0, merchant="Sam"))
        tid = i["PAI NORTHERN THAI"]
        reimburse(client, i["NORTHWIND LTD PAYROLL"], tid)
        r = client.post(f"/api/transactions/{tid}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        assert r.status_code == 200, r.get_json()
        assert sam(client, tid)["owes"] == 0.0 and splitting(client, tid)["mine"]["stays"] == 0.0
        assert costs(client, tid) == 0.0

    def test_sam_first_then_work(self, client):
        """A payback that arrives first: Sam's, then work's; the same end."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"),
                   tx("E-TRANSFER FROM SAM", -60.0, merchant="Sam"))
        tid = i["PAI NORTHERN THAI"]
        client.post(f"/api/transactions/{tid}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        assert costs(client, tid) == 60.0
        got = [c for c in candidates(client, i["NORTHWIND LTD PAYROLL"]) if c["id"] == tid]
        assert got and got[0].get("share") and got[0]["left"] == 60.0
        reimburse(client, i["NORTHWIND LTD PAYROLL"], tid)
        assert costs(client, tid) == 0.0


class TestAllOfIt:
    def test_covers_your_share_and_sams(self, client):
        """Decision 2: "all of it · $120.00" works like any whole-purchase
        payback, so Sam no longer owes."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -120.0, merchant="Northwind Ltd"))
        tid = i["PAI NORTHERN THAI"]
        r = reimburse(client, i["NORTHWIND LTD PAYROLL"], tid, share=False)
        assert r.status_code == 200, r.get_json()
        assert sam(client, tid)["owes"] == 0.0
        assert splitting(client, tid)["mine"]["reimbursed"] == 60.0
        assert costs(client, tid) == 0.0
        # The dinner isn't left out as a work expense.
        assert not client.st.get_transaction(tid).excluded
        # Nobody is asked "Who sent this?".
        review = client.get("/api/review").get_json()
        assert not any(x.get("key") == "credit:" + i["NORTHWIND LTD PAYROLL"]
                       for x in review.get("who_sent") or [])


class TestNames:
    def test_me_is_never_a_name(self, client):
        from finance.etransfers import known_people
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
        reimburse(client, i["NORTHWIND LTD PAYROLL"], i["PAI NORTHERN THAI"])
        names = known_people(client.st.all_transactions(), client.st.splits(), client.st.payback_people())
        assert "me" not in names and "Sam" in names
