"""Adding a challenge or moving money in a savings pot gives back the new
row's id on Postgres too (2026-11-25): psycopg has no `lastrowid`, so on the
hosted ledger both failed. Runs against Postgres when
SPENDIE_TEST_DATABASE_URL is set (tests/conftest.py), SQLite otherwise."""

from finance.store import Store


def test_a_challenge_gets_its_id(tmp_path):
    st = Store(str(tmp_path / "c.db"))
    a = st.add_challenge("category", "Less on dining", 200.0, "2026-11-01", "2026-11-30", category="Dining")
    b = st.add_challenge("category", "Less on taxis", 50.0, "2026-11-01", "2026-11-30", category="Transport")
    assert isinstance(a, int) and b != a
    assert st.challenge(b)["title"] == "Less on taxis"


def test_a_pot_draw_gets_its_id(tmp_path):
    st = Store(str(tmp_path / "p.db"))
    bank = st.add_piggy_bank("Trip", 500.0, "monthly", None, "2026-11")
    a = st.add_draw(bank, "2026-11", 40.0, "lent")
    b = st.add_draw(bank, "2026-11", -10.0, "back")
    assert isinstance(a, int) and b != a
