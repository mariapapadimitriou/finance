"""Running Pearl on your own laptop, with no account to sign in to."""

from app import create_app


def test_nothing_to_approve_and_never_signed_out(tmp_path, monkeypatch):
    """The sign-in approvals check answers with an empty list, not a 401 that
    the page reads as signed out (it showed the welcome screen locally)."""
    for key in ("VERCEL", "DATABASE_URL", "POSTGRES_URL"):
        monkeypatch.delenv(key, raising=False)
    app = create_app(str(tmp_path / "local.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        assert c.get("/api/auth/status").get_json()["signed_in"] is True
        r = c.get("/api/auth/approvals")
    assert r.status_code == 200 and r.get_json() == {"approvals": []}
