"""Spendie — personal finance and budgeting across every card.

Aggregates transactions across every credit card you own, works out where the
money actually goes, and tells you specifically what to cut.

    python app.py            # API on http://localhost:5050
    python app.py --demo     # load sample data first, for a look around

Your data lives in a local SQLite file (`ledger.db`) and never leaves the
machine unless you explicitly run the optional Claude narrative.

This module also exposes a module-level `app` so a WSGI host (Vercel's Flask
runtime, gunicorn, uWSGI) can import it directly. See `_hosted_db_path` for the
one thing that changes when hosted.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import timedelta

from flask import Flask, abort, g, jsonify, request, send_from_directory, session
from flask_cors import CORS

from finance import auth, mailer, users
from finance.api import bp
# storage_mode is re-exported for convenience; /api/health reads it from db.
from finance.db import database_url, is_hosted as _is_hosted, storage_mode  # noqa: F401
from finance.store import DEFAULT_DB, Store

PORT = int(os.environ.get("PORT", 5050))

HERE = os.path.dirname(os.path.abspath(__file__))
# `npm run build` writes here. Vercel also serves this directory from its CDN,
# so in practice Flask only serves it when running as a plain WSGI app.
FRONTEND_DIR = os.path.join(HERE, "public")

# Local dev runs the UI on Vite's dev server against the API on another port.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000",
               "http://localhost:5173", "http://127.0.0.1:5173"]


def _hosted_db_path() -> str | None:
    """On a serverless host without a database, the only writable dir is /tmp.

    Returns None when running normally, so the local SQLite file is used.

    /tmp belongs to one function instance and is discarded when that instance
    is recycled, so anything added there — an upload, a budget, a category you
    corrected — lives only as long as that instance, and a second request
    served by a different instance never sees it at all. Set `DATABASE_URL` to
    a hosted Postgres and none of that applies: `finance/db.py` takes over, the
    path below is ignored, and edits persist and are shared across instances.
    """
    if database_url():
        return None  # Postgres is in charge; the path is unused
    if os.environ.get("LEDGER_DB"):
        return None  # explicit configuration wins
    if _is_hosted():
        return "/tmp/ledger.db"
    return None


# ── Accounts and the sign-in gate ────────────────────────────────────────────
# Registered before the blueprint so it covers every route, present and future.
# See finance/auth.py for why it fails closed when hosted, and finance/users.py
# for how each account gets a ledger of its own.

# Reachable without a session: the sign-in endpoints themselves, and the static
# files the sign-in screen is made of. Everything else, including every /api
# route and the frontend shell, needs one.
_OPEN_PATHS = frozenset({"/api/auth/status", "/api/auth/login", "/api/auth/signup",
                         "/api/auth/forgot", "/api/auth/reset"})


def _is_static_asset(path: str) -> bool:
    return path.startswith("/assets/") or path in ("/favicon.svg", "/favicon.ico")


def _session_key(base: Store) -> bytes:
    """The cookie-signing key: the same on every instance of a deployment.

    The secret-box key when there is one (it is already a stable deployment
    secret), else the owner's configured hash, else a random value kept in the
    database — which every instance reads alike.
    """
    from finance.secrets_box import KEY_ENV
    secret = os.environ.get(KEY_ENV, "").strip()
    if secret:
        return hashlib.sha256(b"spendie.session.v2|" + secret.encode()).digest()
    owner = users.owner_hash_from_env()
    if owner:
        return auth.session_secret(owner)
    return hashlib.sha256(b"spendie.session.v2|"
                          + users.stored_secret(base, "session").encode()).digest()


def _install_auth(app: Flask) -> None:
    base: Store = app.config["STORE"]
    users.bootstrap_owner(base)

    # Cookie hardening. Secure only when hosted, because a local dev server is
    # http and a Secure cookie would simply never be sent.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_is_hosted(),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app.secret_key = _session_key(base)
    app.config["STORES"] = {}

    has_accounts = {"yes": users.count(base) > 0}

    def accounts_exist() -> bool:
        # Once there is an account there always is one, so a yes is kept and
        # only a no is asked again.
        if not has_accounts["yes"]:
            has_accounts["yes"] = users.count(base) > 0
        return has_accounts["yes"]

    def required() -> bool:
        # Hosted: always. Locally, only once there is an account to sign in
        # to — a login prompt in front of a SQLite file on your own laptop
        # helps nobody.
        return _is_hosted() or accounts_exist()

    def store_for(user) -> Store:
        if user.owner:
            return base
        stores = app.config["STORES"]
        if user.id not in stores:
            path, schema = users.ledger_location(base.path, user)
            stores[user.id] = Store(path, base.url, schema)
        return stores[user.id]

    app.config["STORE_FOR"] = store_for

    def signed_in_user():
        user = users.by_id(base, session.get("uid"))
        if user is None or session.get("pw") != user.fingerprint:
            return None
        return user

    def start_session(user) -> None:
        session.clear()
        session["uid"] = user.id
        session["pw"] = user.fingerprint
        session.permanent = True

    # ── Email: a link for a forgotten password ──────────────────────────────
    def public_url() -> str:
        # A link in an email must not be built from a Host header a stranger
        # can set, so the deployment's own address wins when it is known.
        configured = os.environ.get("SPENDIE_PUBLIC_URL", "").strip().rstrip("/")
        if configured:
            return configured
        vercel = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
        if vercel:
            return f"https://{vercel}"
        return request.host_url.rstrip("/")

    @app.before_request
    def _require_sign_in():
        g.user = None
        if not required():
            return None

        path = request.path
        if not accounts_exist():
            if path == "/api/auth/status":
                return None
            # Hosted with no account and nothing to create the first one from.
            # Serving the app would expose it; serving nothing says why.
            return jsonify({
                "error": "This deployment has no account set up, so it will not "
                         "serve anything. Set SPENDIE_OWNER_PASSWORD_HASH in the "
                         "project's environment variables and redeploy.",
                "setup_required": True,
            }), 503

        g.user = signed_in_user()
        if path in _OPEN_PATHS or _is_static_asset(path):
            return None
        if g.user is not None:
            return None

        if path.startswith("/api/"):
            return jsonify({"error": "Sign in first.", "unauthorized": True}), 401

        # A browser asking for a page gets the app shell, which renders the
        # sign-in screen once /api/auth/status tells it to. Redirecting would
        # break deep links for no benefit.
        index = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return send_from_directory(FRONTEND_DIR, "index.html")
        return jsonify({"error": "Sign in first.", "unauthorized": True}), 401

    @app.get("/api/auth/status")
    def _auth_status():
        need = required()
        user = g.get("user")
        return jsonify({
            "required": need,
            "configured": accounts_exist(),
            "signed_in": (not need) or user is not None,
            "user": user.public() if user else None,
            "mail": mailer.configured(),
        })

    @app.post("/api/auth/login")
    def _auth_login():
        if not required():
            return jsonify({"ok": True, "signed_in": True})
        body = request.get_json(silent=True) or {}
        user = users.authenticate(base, body.get("username", ""),
                                  str(body.get("password", "")))
        if user is None:
            # The same message whatever went wrong, so it never confirms that
            # a username exists or that a guess was partly right.
            return jsonify({"error": "That username and password don't match."}), 401
        start_session(user)
        return jsonify({"ok": True, "signed_in": True, "user": user.public()})

    @app.post("/api/auth/forgot")
    def _auth_forgot():
        if not mailer.configured():
            return jsonify({"error": "Email isn't set up on this deployment yet, "
                                     "so a reset link can't be sent."}), 503
        body = request.get_json(silent=True) or {}
        user = users.by_identifier(base, body.get("identifier", ""))
        if user is not None and user.email:
            token = users.issue_reset(base, user.id)
            if token:
                link = f"{public_url()}/?reset={token}"
                try:
                    mailer.send(user.email, "Reset your Spendie password",
                                f"Hi {user.username},\n\nTo choose a new "
                                f"password, open this link within 30 minutes:\n\n"
                                f"{link}\n\nIt works once. If you didn't ask "
                                "for this, ignore this email — your password "
                                "hasn't changed.")
                except Exception:                      # noqa: BLE001
                    pass
        # The same answer whether or not the account exists, so this can't be
        # used to find out who has one.
        return jsonify({"ok": True, "message": "If that account exists, a reset "
                                               "link is on its way to its email."})

    @app.post("/api/auth/reset")
    def _auth_reset():
        body = request.get_json(silent=True) or {}
        password = str(body.get("password", ""))
        if len(password) < users.MIN_PASSWORD:
            return jsonify({"error": f"Passwords need at least "
                                     f"{users.MIN_PASSWORD} characters."}), 400
        user = users.redeem_reset(base, str(body.get("token", "")))
        if user is None:
            return jsonify({"error": "That reset link has expired or was already "
                                     "used. Ask for a new one."}), 400
        users.set_password(base, user.id, auth.hash_password(password))
        users.mark_verified(base, user.id)     # they proved they own the inbox
        user = users.by_id(base, user.id)
        start_session(user)                    # every other session is now void
        return jsonify({"ok": True, "signed_in": True, "user": user.public()})

    @app.post("/api/auth/email")
    def _auth_email():
        """Change your email: where a reset link would be sent."""
        user = g.get("user")
        if user is None:
            return jsonify({"error": "Sign in first.", "unauthorized": True}), 401
        body = request.get_json(silent=True) or {}
        email = users.normalise(body.get("email"))
        problem = users.check_email(email)
        if problem:
            return jsonify({"error": problem}), 400
        if not users.set_email(base, user.id, email):
            return jsonify({"error": "Another account uses that email."}), 409
        if mailer.configured() and user.email and user.email != email:
            # A heads-up to the old address, in case it wasn't them: whoever
            # controls the email controls the account.
            try:
                mailer.send(user.email, "Your Spendie email changed",
                            f"The email on your Spendie account ({user.username}) "
                            f"is now {email}. If that wasn't you, reset your "
                            "password straight away.")
            except Exception:                          # noqa: BLE001
                pass
        return jsonify({"ok": True, "user": users.by_id(base, user.id).public()})

    @app.post("/api/auth/signup")
    def _auth_signup():
        body = request.get_json(silent=True) or {}
        username = users.normalise(body.get("username"))
        password = str(body.get("password", ""))
        email = users.normalise(body.get("email"))
        problem = users.check_new(username, password)
        if not problem and (email or mailer.configured()):
            # Asked for whenever email works, since it is where a reset link
            # goes; optional only where none can be sent.
            problem = users.check_email(email)
        if problem:
            return jsonify({"error": problem}), 400
        if email and users.by_email(base, email) is not None:
            return jsonify({"error": "Another account uses that email."}), 409
        # The first account on a ledger that has none takes the ledger that is
        # already there; every later one starts a ledger of its own.
        first = not accounts_exist()
        user = users.create(base, username, auth.hash_password(password), owner=first)
        if user is None:
            return jsonify({"error": "That username is taken."}), 409
        if email:
            users.set_email(base, user.id, email)
            user = users.by_id(base, user.id)
        store_for(user)                   # its ledger exists from the start
        start_session(user)
        return jsonify({"ok": True, "signed_in": True, "user": user.public()})

    @app.post("/api/auth/password")
    def _auth_password():
        user = g.get("user")
        if user is None:
            return jsonify({"error": "Sign in first.", "unauthorized": True}), 401
        body = request.get_json(silent=True) or {}
        if not auth.verify_password(str(body.get("current", "")), user.password_hash):
            return jsonify({"error": "Your current password isn't right."}), 400
        new = str(body.get("new", ""))
        if len(new) < users.MIN_PASSWORD:
            return jsonify({"error": f"Passwords need at least "
                                     f"{users.MIN_PASSWORD} characters."}), 400
        users.set_password(base, user.id, auth.hash_password(new))
        # Every other session is signed out; this one carries on.
        start_session(users.by_id(base, user.id))
        return jsonify({"ok": True})

    @app.post("/api/auth/logout")
    def _auth_logout():
        session.clear()
        return jsonify({"ok": True, "signed_in": False})


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)

    # CORS exists only for local development, where the Vite dev server and the
    # API sit on different ports. A built deployment serves both from one
    # origin, so sending these headers there would be noise at best.
    if not _is_hosted():
        CORS(app, origins=DEV_ORIGINS)

    app.config["STORE"] = Store(db_path or _hosted_db_path() or DEFAULT_DB)
    _install_auth(app)
    app.register_blueprint(bp)

    # A hosted instance boots with an empty database, so the committed ledger is
    # loaded into it. On /tmp that happens on every cold start; on Postgres it
    # happens once, because `seed_ledger_if_empty` does nothing to a store that
    # already holds transactions — which is what lets an upload there survive.
    if _is_hosted() or os.environ.get("SEED_LEDGER") == "1":
        seed_ledger_if_empty(app.config["STORE"])
    elif os.environ.get("SEED_DEMO") == "1":
        seed_demo_if_empty(app.config["STORE"])

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path: str):
        """Serve the built UI, falling back to API info when there is no build.

        The blueprint's routes are static rules, so Flask matches them ahead of
        this catch-all; the guard below only covers unknown /api paths.
        """
        if path.startswith("api/"):
            abort(404)

        candidate = os.path.join(FRONTEND_DIR, path)
        if path and os.path.isfile(candidate):
            return send_from_directory(FRONTEND_DIR, path)

        if os.path.isfile(os.path.join(FRONTEND_DIR, "index.html")):
            return send_from_directory(FRONTEND_DIR, "index.html")

        return jsonify({
            "app": "Spendie",
            "note": "No frontend build found. Run `npm run build`, "
                    "or `npm run dev` for the dev server.",
            "endpoints": sorted(
                str(r.rule) for r in app.url_map.iter_rules()
                if str(r.rule).startswith("/api")
            ),
        })

    return app


def seed_demo_if_empty(store: Store) -> int:
    """Load generated sample data into an empty ledger. Never touches existing data."""
    if store.all_transactions():
        return 0
    from sample_data.generate import load_demo
    return load_demo(store)


def seed_ledger_if_empty(store: Store) -> int:
    """Load the committed ledger into an empty store, if there is one.

    This is what makes a hosted deployment show real spending rather than an
    empty state on its first boot. Anything in seed_data/transactions.json is
    public by design; see that package's docstring.

    An empty ledger is not always a new one. After a deliberate reset it is
    empty because someone emptied it, and reloading the committed file on the
    next cold start would silently undo that — so the reset leaves a marker
    and this respects it.
    """
    if store.seed_suppressed():
        return 0
    from seed_data.export import load
    return load(store)


# Imported by WSGI hosts. Safe at import time: it opens the ledger and,
# on a hosted instance, seeds an empty one.
app = create_app()


def main() -> int:
    parser = argparse.ArgumentParser(description="Spendie — personal finance API")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--db", default=DEFAULT_DB, help="path to the SQLite ledger")
    parser.add_argument("--demo", action="store_true",
                        help="generate and import sample data before starting")
    parser.add_argument("--reset", action="store_true",
                        help="clear all transactions before starting")
    args = parser.parse_args()

    local = create_app(args.db)
    store: Store = local.config["STORE"]

    if args.reset:
        print(f"Cleared {store.clear_transactions()} transactions.")

    if args.demo:
        from sample_data.generate import load_demo
        print(f"Loaded {load_demo(store)} sample transactions across 3 cards.")

    print(f"Spendie API → http://localhost:{args.port}")
    print(f"Spendie DB  → {args.db}")
    local.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
