"""Income and recurring bills, confirmed (THL-45, THL-127 I-01 to I-06).

Detection (pay candidates, rent by e-Transfer), the answers persisting, and
what they do to safe-to-spend and the path. The person is X-01's: Northwind
pay on the 1st and the 16th, five bills, rent to Parkside — see
test_safe_to_spend — on Friday October 9.
"""

from datetime import date

import pytest

from finance import income_bills as ib, milestones, safe_to_spend as sts
from test_safe_to_spend import TODAY, history, october, row, tx

ANCHOR = {"started": False, "first_stop_done": False, "earned": False,
          "first_stop": 500, "target": 0}


def rows():
    return history() + october()


def state(**kw):
    s = ib.empty()
    s.update(kw)
    return s


def etransfers(amount=1450.00, months=("07", "08", "09", "10"), to="J SMITH", day="01"):
    return [tx(f"2026-{m}-{day}", f"E-TRANSFER TO {to}", amount, "Transfers") for m in months]


NORTHWIND = {"id": "p1", "payer": "Northwind Ltd", "name": "Northwind Ltd", "amount": 2150.00,
             "cadence": "semimonthly", "next": "2026-10-16"}


# ── I-01: what can be pay ────────────────────────────────────────────────

class TestPayCandidates:
    def test_regular_pay_from_an_employer(self):
        [c] = ib.pay_candidates(rows(), TODAY)
        assert (c["payer"], c["amount"], c["cadence"]) == ("Northwind Ltd", 2150.00, "semimonthly")
        assert c["last"] == "2026-10-01" and c["next"] == "2026-10-16"

    def test_repayments_are_never_pay(self):
        """e-Transfers matched to a split (THL-124) never count, however
        regular they are."""
        back = [tx(d, "Sam Lee", -40.00, "Income", repays="dinner")
                for d in ("2026-08-01", "2026-08-15", "2026-09-01", "2026-09-15")]
        assert [c["payer"] for c in ib.pay_candidates(rows() + back, TODAY)] == ["Northwind Ltd"]

    def test_friends_e_transfers_are_never_pay(self):
        friend = [tx(d, "E-Transfer from Sam", -60.00, "Income")
                  for d in ("2026-08-03", "2026-08-17", "2026-08-31", "2026-09-14", "2026-09-28")]
        assert [c["payer"] for c in ib.pay_candidates(rows() + friend, TODAY)] == ["Northwind Ltd"]

    def test_nor_are_they_income(self):
        """A friend's e-Transfer that isn't linked to a split still isn't
        Income in safe-to-spend (THL-127 I-01)."""
        before = sts.compute(rows(), TODAY)
        after = sts.compute(rows() + [tx("2026-10-05", "E-Transfer from Sam", -60.00, "Income")], TODAY)
        assert row(after, "income")["amount"] == row(before, "income")["amount"]

    def test_interest_and_a_one_off_are_not_pay(self):
        extra = [tx(d, "EQ Bank interest", -3.10, "Income")
                 for d in ("2026-07-31", "2026-08-31", "2026-09-30")]
        extra.append(tx("2026-09-20", "Client A", -900.00, "Income"))
        assert [c["payer"] for c in ib.pay_candidates(rows() + extra, TODAY)] == ["Northwind Ltd"]

    def test_amounts_all_over_the_place_are_not_pay(self):
        odd = [tx(d, "Gig Co", -a, "Income") for d, a in
               (("2026-08-01", 120.0), ("2026-08-15", 900.0), ("2026-09-01", 40.0),
                ("2026-09-15", 600.0))]
        assert "Gig Co" not in [c["payer"] for c in ib.pay_candidates(rows() + odd, TODAY)]

    def test_answered_payers_are_not_asked_again(self):
        assert ib.pay_candidates(rows(), TODAY, state(pay_no=["Northwind Ltd"])) == []
        assert ib.pay_candidates(rows(), TODAY, state(pays=[NORTHWIND])) == []


# ── I-04: rent by e-Transfer ─────────────────────────────────────────────

class TestRentByETransfer:
    def test_a_monthly_e_transfer_at_a_similar_amount_is_asked_about(self):
        found = ib.bills(rows() + etransfers(), TODAY, None)
        q = ib.rent_question(found)
        assert q["recipient"] == "J Smith" and q["amount"] == 1450.00 and q["day"] == 1
        r = next(b for b in found if b.get("question"))
        assert r["ticked"] is False and r["name"] == "e-Transfer to J Smith"

    def test_it_stays_out_of_bills_until_she_says_yes(self):
        assert row(sts.compute(rows() + etransfers(months=("07", "08", "09")), TODAY),
                   "bills")["amount"] == 363.48

    def test_no_question_without_the_pattern(self):
        assert ib.rent_question(ib.bills(rows(), TODAY, None)) is None
        two = etransfers(months=("08", "09"))
        assert ib.rent_question(ib.bills(rows() + two, TODAY, None)) is None
        varied = [tx(f"2026-{m}-01", "E-TRANSFER TO J SMITH", a, "Transfers")
                  for m, a in (("07", 300.0), ("08", 1450.0), ("09", 80.0), ("10", 900.0))]
        assert ib.rent_question(ib.bills(rows() + varied, TODAY, None)) is None
        small = etransfers(amount=40.0)
        assert ib.rent_question(ib.bills(rows() + small, TODAY, None)) is None

    def test_yes_makes_it_rent_and_it_counts(self):
        sent = etransfers(months=("07", "08", "09"))
        key = ib.rent_question(ib.bills(rows() + sent, TODAY, None))["key"]
        said = state(rent={key[5:]: "yes"}, bills={key: {"state": "yes"}})
        found = ib.bills(rows() + sent, TODAY, said)
        rent = next(b for b in found if b["key"] == key)
        assert rent["name"] == "Rent" and rent["ticked"] and rent["category"] == "Rent & Housing"
        assert ib.rent_question(found) is None
        bills = row(sts.compute(rows() + sent, TODAY, confirm=said), "bills")
        assert any(b["label"] == "Rent" and b["amount"] == 1450.00 for b in bills["lines"])


# ── Answers feed safe to spend ───────────────────────────────────────────

class TestConfirmationsFeedSafeToSpend:
    def test_nothing_changes_before_the_check(self):
        assert sts.compute(rows(), TODAY, confirm=ib.empty()) == sts.compute(rows(), TODAY)

    def test_an_unticked_bill_stops_counting(self):
        said = state(bills_on="2026-10-09", bills={"Netflix": {"state": "no"},
                                                   "Spotify": {"state": "yes"}})
        bills = row(sts.compute(rows(), TODAY, confirm=said), "bills")
        assert bills["amount"] == pytest.approx(363.48 - 16.49)
        assert "Netflix" not in [b["label"] for b in bills["lines"]]
        spotify = next(b for b in bills["lines"] if b["label"] == "Spotify")
        assert spotify["confirmed"] is True and spotify["suggested"] is False

    def test_an_added_bill_counts_from_its_next_due_date(self):
        said = state(added=[{"id": "b1", "name": "Gym", "amount": 45.0, "cadence": "monthly",
                             "next": "2026-10-20", "varies": False}])
        bills = row(sts.compute(rows(), TODAY, confirm=said), "bills")
        assert bills["amount"] == pytest.approx(363.48 + 45)
        gym = next(b for b in bills["lines"] if b["label"] == "Gym")
        assert gym["date"] == "2026-10-20" and gym["added"] is True
        # One not due until next month adds nothing this month.
        later = state(added=[{**said["added"][0], "next": "2026-11-01"}])
        assert row(sts.compute(rows(), TODAY, confirm=later), "bills")["amount"] == 363.48

    def test_an_edited_bill_counts_with_her_amount(self):
        said = state(bills={"Hydro One": {"state": "yes", "name": "Hydro", "amount": 75.0,
                                          "cadence": "monthly", "next": "2026-10-21",
                                          "varies": True}})
        hydro = next(b for b in row(sts.compute(rows(), TODAY, confirm=said), "bills")["lines"]
                     if b["label"] == "Hydro")
        assert hydro["amount"] == 75.0 and hydro["date"] == "2026-10-21" and hydro["estimate"]

    def test_confirmed_pay_drives_money_coming_in(self):
        said = state(income_on="2026-10-09", pays=[NORTHWIND])
        r = sts.compute(rows(), TODAY, confirm=said)
        assert r["income_source"] == "confirmed"
        assert row(r, "income")["amount"] == 4300.00
        assert r["next_pay"] == "2026-10-16"

    def test_edited_pay_drives_it_too(self):
        """She said the amount was off: $2,300 every two weeks from Oct 16."""
        said = state(income_on="2026-10-09", pays=[{**NORTHWIND, "amount": 2300.0,
                                                     "cadence": "biweekly", "next": "2026-10-16"}])
        r = sts.compute(rows(), TODAY, confirm=said)
        inc = row(r, "income")
        # $2,150 already arrived on the 1st (it's what landed), then Oct 16 and 30.
        assert inc["amount"] == pytest.approx(2150 + 2300 + 2300)
        assert [line["date"] for line in inc["lines"] if not line["arrived"]] == [
            "2026-10-16", "2026-10-30"]

    def test_pay_added_by_hand_counts_from_today(self):
        said = state(income_on="2026-10-09", pays=[{"id": "p2", "payer": "", "name": "Café shifts",
                                                     "amount": 500.0, "cadence": "weekly",
                                                     "next": "2026-10-10"}])
        inc = row(sts.compute(rows(), TODAY, confirm=said), "income")
        assert [line["date"] for line in inc["lines"] if not line["arrived"]] == [
            "2026-10-10", "2026-10-17", "2026-10-24", "2026-10-31"]

    def test_expected_income_from_i03(self):
        """No pay confirmed: what she expects (the told income) counts, and the
        regular pay Pearl guessed at no longer does once she has answered."""
        said = state(income_on="2026-10-09", pay_no=["Northwind Ltd"])
        r = sts.compute(rows(), TODAY, confirm=said, told_income=3800.0)
        assert r["income_source"] == "told" and row(r, "income")["amount"] == 3800.00

    def test_income_that_varies_plans_carefully_once_there_is_data(self):
        irregular = [tx(d, "Client A", -a, "Income") for d, a in
                     (("2026-07-01", 2400.0), ("2026-08-12", 1800.0), ("2026-09-15", 3100.0))]
        said = state(income_on="2026-10-09", varies=True)
        r = sts.compute(irregular, TODAY, confirm=said, told_income=3800.0)
        assert r["income_source"] == "cautious" and row(r, "income")["amount"] == 1800.00
        # Without the history the amount she gave is used.
        r = sts.compute(irregular[-1:], TODAY, confirm=said, told_income=3800.0)
        assert r["income_source"] == "told"


# ── The path ─────────────────────────────────────────────────────────────

class TestThePathUsesTheAnswers:
    def path(self, rows_, s, confirm, **kw):
        kw.setdefault("bills_found", 5)
        return milestones.path(rows_, TODAY, s, anchor=ANCHOR, confirm=confirm, **kw)

    def test_income_is_confirmed_by_her_answer(self):
        loblaws = [tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        s = sts.compute(loblaws, TODAY)
        p = self.path(loblaws, s, state(income_on="2026-10-09", pays=[NORTHWIND]))
        assert p["steps"][0]["done"] is True
        # Answered, but skipped I-03 and confirmed nothing: not confirmed.
        p = self.path(loblaws, s, state(income_on="2026-10-09"))
        assert p["steps"][0]["done"] is False and p["next"]["action"] == "income"

    def test_a_cautious_guess_is_not_a_confirmation(self):
        irregular = [tx(d, "Client A", -a, "Income") for d, a in
                     (("2026-07-01", 2400.0), ("2026-08-12", 1800.0), ("2026-09-15", 3100.0))]
        s = sts.compute(irregular, TODAY)
        assert s["income_source"] == "usual"                 # an estimate from past months
        assert self.path(irregular, s, None)["steps"][0]["done"] is False

    def test_bills_are_confirmed_once_she_confirms_i04(self):
        loblaws = [tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        s = sts.compute(loblaws, TODAY, told_income=3200.0)
        assert self.path(loblaws, s, None, bills_found=0)["next"]["action"] == "bills"
        p = self.path(loblaws, s, state(bills_on="2026-10-09"), bills_found=0)
        assert p["steps"][1]["done"] is True

    def test_before_the_check_the_earlier_reading_holds(self):
        p = self.path(rows(), sts.compute(rows(), TODAY, savings_target=300.0), None)
        assert p["phase"] == "build"


# ── Validation ───────────────────────────────────────────────────────────

class TestValidation:
    def test_pay(self):
        ok, err = ib.pay_from({"name": " Northwind ", "amount": "$2,150", "cadence": "biweekly",
                               "next": "2026-10-16"})
        assert err is None and ok["name"] == "Northwind" and ok["amount"] == 2150.0
        for bad in ({"amount": 1, "cadence": "weekly", "next": "2026-10-16"},
                    {"name": "x", "amount": 0, "cadence": "weekly", "next": "2026-10-16"},
                    {"name": "x", "amount": "lots", "cadence": "weekly", "next": "2026-10-16"},
                    {"name": "x", "amount": 10, "cadence": "fortnightly", "next": "2026-10-16"},
                    {"name": "x", "amount": 10, "cadence": "weekly", "next": "soon"}):
            assert ib.pay_from(bad)[1]
        assert ib.pay_from({"name": "x", "amount": 10, "cadence": "irregular"})[1] is None

    def test_bill(self):
        assert ib.bill_from({"name": "Gym", "amount": 45, "cadence": "monthly",
                             "next": "2026-11-01"})[1] is None
        assert ib.bill_from({"name": "Gym", "amount": -45, "cadence": "monthly",
                             "next": "2026-11-01"})[1]
        assert ib.bill_from({"name": "Gym", "amount": 45, "cadence": "daily",
                             "next": "2026-11-01"})[1]

    def test_schedules(self):
        d = date
        assert ib.occurrences(d(2026, 10, 16), "biweekly", d(2026, 10, 1), d(2026, 10, 31)) == [
            d(2026, 10, 2), d(2026, 10, 16), d(2026, 10, 30)]
        assert ib.occurrences(d(2026, 10, 16), "semimonthly", d(2026, 10, 1), d(2026, 10, 31)) == [
            d(2026, 10, 1), d(2026, 10, 16)]
        assert ib.occurrences(d(2026, 8, 21), "bimonthly", d(2026, 10, 1), d(2026, 10, 31)) == [
            d(2026, 10, 21)]
        assert ib.occurrences(d(2026, 9, 21), "bimonthly", d(2026, 10, 1), d(2026, 10, 31)) == []


# ── The endpoints ────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    import finance.api as api
    import finance.income_bills_api as iba
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    monkeypatch.setattr(iba, "_today_iso", lambda: TODAY.isoformat())
    app = create_app(str(tmp_path / "ib.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.application.config["STORE"].add_transactions(rows() + etransfers(months=("07", "08", "09")))
        yield c


def home(c):
    return c.get("/api/home").get_json()["safe_to_spend"]


class TestTheEndpoints:
    def test_the_check_as_she_sees_it(self, client):
        d = client.get("/api/income-bills").get_json()
        assert [c["payer"] for c in d["candidates"]] == ["Northwind Ltd"]
        assert d["rent_question"]["recipient"] == "J Smith"
        assert d["checked"] == {"income": None, "bills": None}
        # Before she answers, income is Pearl's estimate from her last 3 months.
        assert d["totals"]["income"] == d["expected"]["estimate"] == 3583.33

    def test_the_whole_flow_persists_and_drives_home(self, client):
        before = home(client)
        d = client.post("/api/income-bills/pay/answer",
                        json={"payer": "Northwind Ltd", "answer": "yes"}).get_json()
        assert d["pays"][0]["name"] == "Northwind Ltd" and d["checked"]["income"] == TODAY.isoformat()
        assert d["totals"]["income"] == 4300.0
        key = d["rent_question"]["key"]
        d = client.post("/api/income-bills/rent", json={"key": key}).get_json()
        assert d["rent_question"] is None
        rent = next(b for b in d["bills"] if b["key"] == key)
        assert rent["name"] == "Rent" and rent["ticked"]
        d = client.post("/api/income-bills/bills", json={
            "name": "Gym membership", "amount": "45", "cadence": "monthly",
            "next": "2026-10-20"}).get_json()
        ticked = {b["key"]: b["key"] != "Netflix" for b in d["bills"]}
        d = client.put("/api/income-bills/bills", json={"ticked": ticked}).get_json()
        assert d["checked"]["bills"] == TODAY.isoformat()

        after = home(client)
        assert after["income_source"] == "confirmed"
        labels = [b["label"] for b in next(r for r in after["rows"] if r["key"] == "bills")["lines"]]
        assert "Gym membership" in labels and "Netflix" not in labels
        assert after["amount"] != before["amount"]
        # The rent e-Transfers are Rent (Essentials) now, remembered for J Smith.
        st = client.application.config["STORE"]
        assert {t.category for t in st.all_transactions() if "SMITH" in t.description} == {
            "Rent & Housing"}
        assert any(k == "name:j smith" for k in st.destinations())
        # The old plan's take-home follows her confirmed pay.
        assert st.float_setting("monthly_income") == 4300.0
        # And the path counts both as confirmed.
        steps = client.get("/api/path").get_json()
        assert steps["phase"] != "protect" or all(s["done"] for s in steps["steps"][:2])

    def test_editing_and_removing_pay(self, client):
        d = client.post("/api/income-bills/pay", json={
            "payer": "Northwind Ltd", "name": "Northwind payroll", "amount": 2300,
            "cadence": "biweekly", "next": "2026-10-16"}).get_json()
        [p] = d["pays"]
        assert p["amount"] == 2300 and p["payer"] == "Northwind Ltd"
        assert d["candidates"] == []
        d = client.put(f"/api/income-bills/pay/{p['id']}", json={
            "name": "Northwind payroll", "amount": 2400, "cadence": "biweekly",
            "next": "2026-10-16"}).get_json()
        assert d["pays"][0]["amount"] == 2400
        inc = row(home(client), "income")
        arrived = sum(line["amount"] for line in inc["lines"] if line["arrived"])
        assert inc["amount"] == pytest.approx(arrived + 2400 * 2)
        assert [line["date"] for line in inc["lines"] if not line["arrived"]] == [
            "2026-10-16", "2026-10-30"]
        assert client.delete(f"/api/income-bills/pay/{p['id']}").get_json()["pays"] == []
        assert client.delete("/api/income-bills/pay/nope").status_code == 404

    def test_no_its_something_else_then_expected_income(self, client):
        d = client.post("/api/income-bills/pay/answer",
                        json={"payer": "Northwind Ltd", "answer": "no"}).get_json()
        assert d["candidates"] == [] and d["pays"] == []
        d = client.put("/api/income-bills/expected", json={"amount": "$3,800", "varies": False}).get_json()
        assert d["expected"]["amount"] == 3800.0 and d["expected"]["varies"] is False
        assert d["totals"]["income"] == 3800.0
        s = home(client)
        assert s["income_source"] == "told" and row(s, "income")["amount"] == 3800.0

    def test_removing_a_bill_and_undo(self, client):
        d = client.delete("/api/income-bills/bills/Netflix").get_json()
        assert d["removed"]["key"] == "Netflix" and d["removed"]["amount"] == 16.49
        assert not next(b for b in d["bills"] if b["key"] == "Netflix")["ticked"]
        undo = {k: v for k, v in d["removed"].items() if k != "key"}
        d = client.put("/api/income-bills/bills/Netflix", json=undo).get_json()
        assert next(b for b in d["bills"] if b["key"] == "Netflix")["ticked"]
        d = client.post("/api/income-bills/bills", json={
            "name": "Gym", "amount": 45, "cadence": "monthly", "next": "2026-11-01"}).get_json()
        added = next(b for b in d["bills"] if b["source"] == "added")
        d = client.delete(f"/api/income-bills/bills/{added['key']}").get_json()
        assert not any(b["source"] == "added" for b in d["bills"])

    @pytest.mark.parametrize("path,method,body", [
        ("/api/income-bills/pay/answer", "post", {"payer": "Northwind Ltd", "answer": "maybe"}),
        ("/api/income-bills/pay", "post", {"name": "", "amount": 10, "cadence": "weekly",
                                           "next": "2026-10-16"}),
        ("/api/income-bills/pay", "post", {"name": "X", "amount": "lots", "cadence": "weekly",
                                           "next": "2026-10-16"}),
        ("/api/income-bills/expected", "put", {"amount": 0}),
        ("/api/income-bills/expected", "put", {"amount": "a lot"}),
        ("/api/income-bills/bills", "put", {"ticked": ["Netflix"]}),
        ("/api/income-bills/bills", "post", {"name": "Gym", "amount": 45, "cadence": "daily",
                                             "next": "2026-11-01"}),
        ("/api/income-bills/bills/Netflix", "put", {"name": "Netflix", "amount": 16.49,
                                                    "cadence": "monthly", "next": "never"}),
    ])
    def test_bad_input_is_refused_with_a_reason(self, client, path, method, body):
        r = getattr(client, method)(path, json=body)
        assert r.status_code == 400 and r.get_json()["error"]

    def test_unknown_things_are_not_found(self, client):
        assert client.post("/api/income-bills/pay/answer",
                           json={"payer": "Nobody", "answer": "yes"}).status_code == 404
        assert client.post("/api/income-bills/rent", json={"key": "rent:to:nobody"}).status_code == 404
        assert client.put("/api/income-bills/bills/Nope", json={
            "name": "x", "amount": 1, "cadence": "monthly", "next": "2026-11-01"}).status_code == 404
        assert client.delete("/api/income-bills/bills/added:b9").status_code == 404

    def test_onboarding_has_the_check_between_linking_and_the_path(self):
        from finance import users
        assert users.STEPS.index("linked") < users.STEPS.index("income") < users.STEPS.index("path")

    def test_use_pearls_estimate_clears_her_amount(self, client):
        client.put("/api/income-bills/expected", json={"amount": 6000})
        assert home(client)["income_source"] == "told"
        d = client.delete("/api/income-bills/expected").get_json()
        assert d["expected"]["amount"] is None
        assert home(client)["income_source"] != "told"
