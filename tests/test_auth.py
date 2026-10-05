"""The sign-in gate.

These matter more than most tests here: everything else in this app guards
against getting a number wrong, and this guards against a stranger reaching a
bank connection.
"""

import pytest

from app import create_app
from finance import auth


@pytest.fixture(autouse=True)
def _no_ambient_password(monkeypatch):
    """Stop a password in the developer's own environment from leaking in."""
    monkeypatch.delenv(auth.PASSWORD_ENV, raising=False)
    monkeypatch.delenv(auth.HASH_ENV, raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)


def client_for(tmp_path, monkeypatch, *, hosted=False, password=None, as_hash=True):
    if hosted:
        monkeypatch.setenv("VERCEL", "1")
    if password is not None:
        if as_hash:
            monkeypatch.setenv(auth.HASH_ENV, auth.hash_password(password))
        else:
            monkeypatch.setenv(auth.PASSWORD_ENV, password)
    app = create_app(str(tmp_path / "t.db"))
    app.config.update(TESTING=True)
    return app.test_client()


class TestHashing:
    def test_a_password_verifies_against_its_own_hash(self):
        stored = auth.hash_password("correct horse")
        assert auth.verify_password("correct horse", stored)

    def test_a_wrong_password_does_not(self):
        assert not auth.verify_password("nope", auth.hash_password("correct horse"))

    def test_two_hashes_of_one_password_differ(self):
        """Salted, so the stored value never reveals that two people picked
        the same password — and never matches a rainbow table."""
        a, b = auth.hash_password("same"), auth.hash_password("same")
        assert a != b
        assert auth.verify_password("same", a) and auth.verify_password("same", b)

    @pytest.mark.parametrize("junk", ["", "garbage", "md5$aa$bb", "scrypt$zz"])
    def test_a_malformed_stored_hash_rejects_rather_than_raising(self, junk):
        assert auth.verify_password("anything", junk) is False

    def test_the_session_key_is_derived_and_stable(self):
        """It has to survive across serverless instances, or every other
        request would land on one that signed cookies with a different key."""
        stored = auth.hash_password("pw")
        assert auth.session_secret(stored) == auth.session_secret(stored)
        assert auth.session_secret(stored) != auth.session_secret(auth.hash_password("pw"))

    def test_the_session_key_is_not_the_hash(self):
        stored = auth.hash_password("pw")
        assert auth.session_secret(stored).hex() != stored


class TestHostedWithoutAPassword:
    """The mistake most likely to be made, and the one that must not be quiet."""

    def test_it_refuses_to_serve_anything(self, tmp_path, monkeypatch):
        c = client_for(tmp_path, monkeypatch, hosted=True, password=None)
        for path in ("/", "/api/summary", "/api/transactions"):
            r = c.get(path)
            assert r.status_code == 503, path
            assert r.get_json()["setup_required"] is True

    def test_no_spending_data_reaches_the_response(self, tmp_path, monkeypatch):
        c = client_for(tmp_path, monkeypatch, hosted=True, password=None)
        body = c.get("/api/summary").get_json()
        assert set(body) == {"error", "setup_required"}

    def test_logging_in_is_impossible_rather_than_open(self, tmp_path, monkeypatch):
        c = client_for(tmp_path, monkeypatch, hosted=True, password=None)
        assert c.post("/api/auth/login", json={"username": "mariapapas", "password": ""}).status_code == 503


class TestLockedDeployment:
    @pytest.fixture()
    def c(self, tmp_path, monkeypatch):
        return client_for(tmp_path, monkeypatch, hosted=True, password="hunter2")

    def test_the_api_is_closed_until_you_sign_in(self, c):
        r = c.get("/api/summary")
        assert r.status_code == 401
        assert r.get_json()["unauthorized"] is True

    def test_every_route_is_covered_not_just_the_ones_we_remembered(self, c):
        """The gate is a before_request over the whole app, so a route added
        later is protected without anyone having to remember."""
        for path in ("/api/summary", "/api/transactions", "/api/plan",
                     "/api/piggy", "/api/projections", "/api/trips",
                     "/api/accounts", "/api/insights", "/api/budgets"):
            assert c.get(path).status_code == 401, path

    def test_the_destructive_routes_are_covered_too(self, c):
        assert c.delete("/api/transactions").status_code == 401
        assert c.post("/api/import", json={"files": []}).status_code == 401
        assert c.post("/api/recategorize").status_code == 401

    def test_a_wrong_password_is_refused(self, c):
        assert c.post("/api/auth/login", json={"username": "mariapapas", "password": "wrong"}).status_code == 401
        assert c.get("/api/summary").status_code == 401

    def test_the_right_password_opens_it(self, c):
        assert c.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"}).status_code == 200
        assert c.get("/api/summary").status_code == 200

    def test_the_session_persists_across_requests(self, c):
        c.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"})
        assert c.get("/api/summary").status_code == 200
        assert c.get("/api/accounts").status_code == 200

    def test_signing_out_closes_it_again(self, c):
        c.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"})
        assert c.post("/api/auth/logout").status_code == 200
        assert c.get("/api/summary").status_code == 401

    def test_status_is_readable_while_signed_out(self, c):
        """The login screen needs to know a password is wanted before it can
        ask for one."""
        r = c.get("/api/auth/status")
        assert r.status_code == 200
        assert r.get_json() == {"required": True, "configured": True,
                                "signed_in": False, "user": None}

    def test_status_reports_signed_in_after_login(self, c):
        c.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"})
        body = c.get("/api/auth/status").get_json()
        assert body["signed_in"] is True
        assert body["user"]["username"] == "mariapapas"

    def test_a_wrong_username_is_refused_like_a_wrong_password(self, c):
        a = c.post("/api/auth/login", json={"username": "nobody", "password": "hunter2"})
        b = c.post("/api/auth/login", json={"username": "mariapapas", "password": "x"})
        assert a.status_code == b.status_code == 401
        assert a.get_json()["error"] == b.get_json()["error"]

    def test_a_plain_password_env_var_also_works(self, tmp_path, monkeypatch):
        c = client_for(tmp_path, monkeypatch, hosted=True, password="plain",
                       as_hash=False)
        assert c.post("/api/auth/login", json={"username": "mariapapas", "password": "plain"}).status_code == 200

    def test_the_error_message_never_says_which_part_was_wrong(self, c):
        a = c.post("/api/auth/login", json={"username": "mariapapas", "password": ""}).get_json()["error"]
        b = c.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter"}).get_json()["error"]
        assert a == b


class TestRunningLocally:
    """A login prompt in front of a SQLite file on your own laptop helps nobody."""

    def test_no_password_means_no_prompt(self, tmp_path, monkeypatch):
        c = client_for(tmp_path, monkeypatch, hosted=False, password=None)
        assert c.get("/api/summary").status_code == 200
        assert c.get("/api/auth/status").get_json() == {
            "required": False, "configured": False, "signed_in": True, "user": None}

    def test_setting_one_locally_is_honoured(self, tmp_path, monkeypatch):
        c = client_for(tmp_path, monkeypatch, hosted=False, password="local")
        assert c.get("/api/summary").status_code == 401
        assert c.post("/api/auth/login", json={"username": "mariapapas", "password": "local"}).status_code == 200
        assert c.get("/api/summary").status_code == 200

class TestSessionsSurviveAcrossInstances:
    """The bug this class exists for: signing in worked, and then the login
    screen came straight back.

    A serverless deployment runs many instances and any request can land on
    any of them. The session key is derived from the password hash, so if two
    instances compute different hashes for the same password they sign cookies
    with different keys — the login succeeds on the instance that answered it
    and every request after that is rejected. Nothing errors; it just looks
    like a password that will not take.

    Two app objects stand in for two instances, because that is exactly the
    difference between them: a fresh process reading the same environment.
    """

    def two_instances(self, tmp_path, monkeypatch, password, as_hash):
        # Both read one environment variable with one value, which is what
        # two serverless instances of the same deployment actually do. Hashing
        # separately per instance would be testing the fixture, not the app.
        if as_hash:
            monkeypatch.setenv(auth.HASH_ENV, auth.hash_password(password))
        else:
            monkeypatch.setenv(auth.PASSWORD_ENV, password)
        a = client_for(tmp_path / "a", monkeypatch, hosted=True)
        b = client_for(tmp_path / "b", monkeypatch, hosted=True)
        return a, b

    def test_a_plain_password_gives_every_instance_the_same_key(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv(auth.PASSWORD_ENV, "hunter2")
        assert auth.configured_hash() == auth.configured_hash()

    def test_a_session_from_one_instance_works_on_another(
            self, tmp_path, monkeypatch):
        (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
        a, b = self.two_instances(tmp_path, monkeypatch,
                                  password="hunter2", as_hash=False)

        assert a.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"}).status_code == 200
        cookie = a.get_cookie("session")
        assert cookie is not None, "logging in should have set a session cookie"

        b.set_cookie("session", cookie.value, domain="localhost")
        assert b.get("/api/summary").status_code == 200, \
            "the next request can land on any instance; all of them must accept it"

    def test_the_same_holds_for_a_pre_computed_hash(self, tmp_path, monkeypatch):
        (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
        a, b = self.two_instances(tmp_path, monkeypatch,
                                  password="hunter2", as_hash=True)
        a.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"})
        b.set_cookie("session", a.get_cookie("session").value, domain="localhost")
        assert b.get("/api/summary").status_code == 200

    def test_a_different_password_does_not_share_a_session(
            self, tmp_path, monkeypatch):
        """Stability must not become a key that is the same everywhere."""
        (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
        a = client_for(tmp_path / "a", monkeypatch, hosted=True,
                       password="hunter2", as_hash=False)
        a.post("/api/auth/login", json={"username": "mariapapas", "password": "hunter2"})
        stolen = a.get_cookie("session").value

        monkeypatch.setenv(auth.PASSWORD_ENV, "something-else")
        b = client_for(tmp_path / "b", monkeypatch, hosted=True)
        b.set_cookie("session", stolen, domain="localhost")
        assert b.get("/api/summary").status_code == 401

    def test_changing_the_password_signs_existing_sessions_out(
            self, tmp_path, monkeypatch):
        (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
        a = client_for(tmp_path / "a", monkeypatch, hosted=True,
                       password="old-one", as_hash=False)
        a.post("/api/auth/login", json={"username": "mariapapas", "password": "old-one"})
        old_cookie = a.get_cookie("session").value

        monkeypatch.setenv(auth.PASSWORD_ENV, "new-one")
        b = client_for(tmp_path / "b", monkeypatch, hosted=True)
        b.set_cookie("session", old_cookie, domain="localhost")
        assert b.get("/api/summary").status_code == 401
