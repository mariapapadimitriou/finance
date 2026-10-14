"""The safeguards every request gets (finance/security.py, SECURITY.md)."""

from __future__ import annotations

import pytest

from finance import users


@pytest.fixture()
def hosted(tmp_path, monkeypatch):
    """A hosted deployment with one account, signed in."""
    from finance import auth
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV, users.OWNER_USERNAME_ENV,
                users.OWNER_EMAIL_ENV, "SPENDIE_SECRET_KEY", "AWS_LAMBDA_FUNCTION_NAME",
                "SPENDIE_PUBLIC_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("correct horse battery"))
    monkeypatch.setenv(users.OWNER_EMAIL_ENV, "maria@example.com")
    from app import create_app
    app = create_app(str(tmp_path / "h.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        r = c.post("/api/auth/login", json={"username": users.DEFAULT_OWNER,
                                            "password": "correct horse battery"})
        assert r.status_code == 200, r.get_json()
        yield c


def test_every_response_carries_the_headers(hosted):
    r = hosted.get("/api/auth/status")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "cdn.plaid.com" in h["Content-Security-Policy"]
    assert h["Strict-Transport-Security"].startswith("max-age=31536000")
    assert h["Cache-Control"] == "no-store"
    assert "geolocation=()" in h["Permissions-Policy"]


def test_a_change_must_come_from_this_site(hosted):
    bad = hosted.post("/api/review/skip", json={"key": "u:x"},
                      headers={"Origin": "https://evil.example"})
    assert bad.status_code == 403
    ok = hosted.post("/api/review/skip", json={"key": "u:x"},
                     headers={"Origin": "http://localhost"})
    assert ok.status_code != 403
    # A GET is never blocked by origin.
    assert hosted.get("/api/home", headers={"Origin": "https://evil.example"}).status_code == 200


def test_a_huge_body_is_refused_before_it_is_read(hosted):
    r = hosted.post("/api/review/skip", data=b"x" * (11 * 1024 * 1024),
                    content_type="application/json")
    assert r.status_code == 413


def test_a_session_left_idle_is_over_on_the_server(hosted, monkeypatch):
    assert hosted.get("/api/home").status_code == 200
    now = users.now()
    monkeypatch.setattr(users, "now", lambda: now + 21 * 60)
    r = hosted.get("/api/home")
    assert r.status_code == 401 and r.get_json()["timeout"] is True
    # And it stays signed out: the session was cleared.
    monkeypatch.setattr(users, "now", lambda: now + 22 * 60)
    assert hosted.get("/api/home").status_code == 401


def test_sign_in_codes_never_reach_the_hosted_log(hosted, capsys):
    """Hosted without mail refuses to send a code rather than print one."""
    r = hosted.post("/api/auth/code/start", json={"email": "maria@example.com"})
    assert r.status_code in (503, 200)
    assert "Your Pearl code" not in capsys.readouterr().err
