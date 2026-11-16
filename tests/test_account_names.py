"""Short account names (Your accounts v2, AS-01 v2 1415:87857, note
1415:88764): the nickname wins; otherwise the bank plus the product without
"Account", "Card", "®" or "*"; "••last4" only when two would match."""

from __future__ import annotations

import pytest

from finance.account_names import add_short_names, short_name, split_name


def acct(name, institution="", nickname="", mask=""):
    return {"bank_name": name, "institution": institution, "nickname": nickname, "mask": mask}


# --- nickname wins ----------------------------------------------------------

def test_nickname_wins():
    assert short_name("TD Every Day Chequing Account", "TD", nickname="Bills") == "Bills"


def test_nickname_is_trimmed_and_blank_one_ignored():
    assert short_name("TD Every Day Chequing", "TD", nickname="  Rent pot ") == "Rent pot"
    assert short_name("TD Every Day Chequing", "TD", nickname="   ") == "TD Every Day Chequing"


def test_nickname_is_the_short_product_too():
    [r] = add_short_names([acct("Scotia iTRADE TFSA", "Scotia iTRADE", nickname="House fund")])
    assert (r["short_name"], r["short_product"]) == ("House fund", "House fund")


# --- word stripping ---------------------------------------------------------

def test_figma_example_amex_cobalt():
    assert short_name("American Express Cobalt® Card", "American Express") == "Amex Cobalt"


@pytest.mark.parametrize("name, bank, want", [
    ("TD Preferred Chequing Account", "TD", "TD Preferred Chequing"),
    ("Cash Back Visa* Card", "TD", "TD Cash Back Visa"),
    ("Preferred Package", "Scotiabank", "Scotia Preferred Package"),
    ("Scotiabank Mortgage", "Scotiabank", "Scotia Mortgage"),
    ("Wealthsimple Cash", "Wealthsimple", "Wealthsimple Cash"),
    ("Savings Accounts", "Tangerine", "Tangerine Savings"),
    ("Cardinal Rewards", "TD", "TD Cardinal Rewards"),   # whole words only
])
def test_strips_account_card_and_marks(name, bank, want):
    assert short_name(name, bank) == want


def test_bank_is_not_said_twice():
    assert short_name("TD Cash Back Visa", "TD") == "TD Cash Back Visa"
    assert split_name("TD Cash Back Visa", "TD") == ("TD", "Cash Back Visa")


def test_statement_without_a_bank_keeps_its_own_or_shortens_a_known_one():
    assert short_name("American Express Cobalt Card") == "Amex Cobalt"
    assert short_name("Visa Infinite") == "Visa Infinite"


def test_short_bank_and_product_for_the_grouped_row():
    rows = add_short_names([acct("Cash", "Scotia iTRADE"), acct("Group RRSP", "Scotia iTRADE"),
                            acct("TFSA", "Scotia iTRADE")])
    assert {r["short_bank"] for r in rows} == {"Scotia iTRADE"}
    assert [r["short_product"] for r in rows] == ["Cash", "Group RRSP", "TFSA"]
    assert rows[1]["short_name"] == "Scotia iTRADE Group RRSP"


# --- duplicates -------------------------------------------------------------

def test_last4_only_when_two_would_match():
    rows = add_short_names([acct("TD Cash Back Visa Card", "TD", mask="1203"),
                            acct("Cash Back Visa", "TD", mask="7781"),
                            acct("TD Minimum Chequing", "TD", mask="4417")])
    assert [r["short_name"] for r in rows] == [
        "TD Cash Back Visa ••1203", "TD Cash Back Visa ••7781", "TD Minimum Chequing"]
    assert rows[0]["short_product"] == "Cash Back Visa ••1203"


def test_matching_is_case_blind():
    rows = add_short_names([acct("TD CASH BACK VISA", "TD", mask="1"),
                            acct("TD Cash Back Visa", "TD", mask="2")])
    assert all("••" in r["short_name"] for r in rows)


def test_a_nickname_never_gets_digits_but_the_other_does():
    rows = add_short_names([acct("Cobalt", "American Express", nickname="Amex Cobalt", mask="3008"),
                            acct("American Express Cobalt® Card", "American Express", mask="1005")])
    assert [r["short_name"] for r in rows] == ["Amex Cobalt", "Amex Cobalt ••1005"]


# --- in the payload ---------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app import create_app
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, Fernet.generate_key().decode())
    app = create_app(str(tmp_path / "names.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        st = c.application.config["STORE"]
        st.add_plaid_item("item-amex", "token", "American Express")
        st.note_account("cobalt", name="American Express Cobalt® Card ••1005", item_id="item-amex",
                        account_type="credit", subtype="credit card")
        st.note_account("gold", name="American Express Cobalt Card ••3008", item_id="item-amex",
                        account_type="credit", subtype="credit card")
        yield c


def test_overview_carries_short_names(client):
    linked = client.get("/api/accounts/overview").get_json()["linked"]
    by_id = {a["id"]: a for a in linked}
    assert by_id["cobalt"]["short_name"] == "Amex Cobalt ••1005"
    assert by_id["gold"]["short_name"] == "Amex Cobalt ••3008"
    assert by_id["cobalt"]["short_bank"] == "Amex"


def test_a_nickname_takes_over_in_the_payload(client):
    r = client.put("/api/accounts/gold/settings", json={"nickname": "Work card"})
    assert r.status_code == 200
    assert r.get_json()["account"]["short_name"] == "Work card"
    linked = {a["id"]: a for a in client.get("/api/accounts/overview").get_json()["linked"]}
    # No longer two the same: the Cobalt loses its digits.
    assert linked["cobalt"]["short_name"] == "Amex Cobalt"
