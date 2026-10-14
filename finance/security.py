"""What every response and every request gets, so the safeguards PIPEDA
asks for (and Quebec's Law 25, and Plaid's Developer Policy) hold on every
page rather than where someone remembered them. See SECURITY.md.

* Response headers: no framing, no MIME sniffing, no referrer leakage, a
  Content Security Policy that only lets the app's own code and Plaid Link
  run, and HSTS when hosted. API answers are never cached.
* Cross-site requests: a browser request that changes something must come
  from this site. The cookie is SameSite=Lax already; checking Origin as
  well costs nothing and covers old browsers.
* Session idleness: a session unused for `IDLE_SECONDS` is over on the
  server, not just in the browser's timer (A-14).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import jsonify, request

# A-14 signs out after 15 minutes without a touch; the server allows a
# little slack for a request that was already on its way.
IDLE_SECONDS = 20 * 60
# A statement file is a few hundred KB; a 10 MB body is not a statement.
MAX_BODY_BYTES = 10 * 1024 * 1024
UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# Plaid Link is loaded from Plaid's CDN and opens in an iframe of its own.
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.plaid.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://*.plaid.com; "
    "frame-src https://cdn.plaid.com https://*.plaid.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


def _same_site(origin: str | None) -> bool:
    """Whether a request's Origin names this site."""
    if not origin:
        return False
    try:
        o, h = urlsplit(origin), urlsplit(request.host_url)
    except ValueError:
        return False
    return (o.scheme, o.netloc) == (h.scheme, h.netloc)


def install(app, *, hosted: bool, dev_origins: tuple[str, ...] = ()) -> None:
    app.config["HOSTED"] = hosted

    @app.before_request
    def _same_site_only():
        if request.method not in UNSAFE_METHODS or not request.path.startswith("/api/"):
            return None
        origin = request.headers.get("Origin")
        if origin is None:
            # Browsers always send Origin on these methods; a tool or a test
            # doesn't, and a tool can't carry her cookie.
            return None
        if _same_site(origin) or (not hosted and origin in dev_origins):
            return None
        return jsonify({"error": "That request didn't come from Pearl."}), 403

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy",
                                "camera=(), microphone=(), geolocation=(), payment=()")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if hosted:
            resp.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp
