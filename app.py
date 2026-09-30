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
import os
import secrets
import sys
from datetime import timedelta

from flask import Flask, abort, jsonify, request, send_from_directory, session
from flask_cors import CORS

from finance import auth
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


# ── The password gate ────────────────────────────────────────────────────────
# Registered before the blueprint so it covers every route, present and future.
# See finance/auth.py for why it fails closed when hosted.

# Reachable without a session: the login endpoints themselves, and the static
# files the login screen is made of. Everything else, including every /api
# route and the frontend shell, needs one.
_OPEN_PATHS = frozenset({"/api/auth/status", "/api/auth/login"})


def _is_static_asset(path: str) -> bool:
    return path.startswith("/assets/") or path in ("/favicon.svg", "/favicon.ico")


def _install_auth(app: Flask) -> None:
    password_hash = auth.configured_hash()
    app.config["AUTH_REQUIRED"] = auth.required(_is_hosted())
    app.config["AUTH_HASH"] = password_hash

    # Cookie hardening. Secure only when hosted, because a local dev server is
    # http and a Secure cookie would simply never be sent.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_is_hosted(),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    if password_hash:
        app.secret_key = auth.session_secret(password_hash)
    else:
        # No password, so nothing is signed that matters. A random key keeps
        # Flask happy and guarantees nothing is silently carried over if a
        # password is added later.
        app.secret_key = secrets.token_bytes(32)

    @app.before_request
    def _require_password():
        if not app.config["AUTH_REQUIRED"]:
            return None

        if not app.config["AUTH_HASH"]:
            # Hosted with no password configured. Serving the app would expose
            # it; serving nothing at least says why.
            return jsonify({
                "error": "This deployment has no password set, so it will not "
                         "serve anything. Set SPENDIE_PASSWORD_HASH in the "
                         "project's environment variables and redeploy.",
                "setup_required": True,
            }), 503

        path = request.path
        if path in _OPEN_PATHS or _is_static_asset(path):
            return None
        if session.get("ok") is True:
            return None

        if path.startswith("/api/"):
            return jsonify({"error": "Sign in first.", "unauthorized": True}), 401

        # A browser asking for a page gets the app shell, which renders the
        # login screen once /api/auth/status tells it to. Redirecting would
        # break deep links for no benefit.
        index = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return send_from_directory(FRONTEND_DIR, "index.html")
        return jsonify({"error": "Sign in first.", "unauthorized": True}), 401

    @app.get("/api/auth/status")
    def _auth_status():
        return jsonify({
            "required": bool(app.config["AUTH_REQUIRED"]),
            "configured": bool(app.config["AUTH_HASH"]),
            "signed_in": (not app.config["AUTH_REQUIRED"]) or session.get("ok") is True,
        })

    @app.post("/api/auth/login")
    def _auth_login():
        if not app.config["AUTH_REQUIRED"]:
            return jsonify({"ok": True, "signed_in": True})
        stored = app.config["AUTH_HASH"]
        if not stored:
            return jsonify({"error": "No password is configured."}), 503

        body = request.get_json(silent=True) or {}
        if not auth.verify_password(str(body.get("password", "")), stored):
            # The same message whatever went wrong, so it never confirms a
            # partially-right guess.
            return jsonify({"error": "That password isn't right."}), 401

        session.clear()
        session["ok"] = True
        session.permanent = True
        return jsonify({"ok": True, "signed_in": True})

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
    """Load the committed ledger into an empty store.

    This is what makes a hosted deployment show real spending rather than an
    empty state. Everything in seed_data/transactions.json is public by design;
    see that package's docstring.
    """
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
