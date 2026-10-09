"""Six-digit codes sent by email: how a Pearl account is made, and one of two
ways back in (the other is a passkey).

A code is stored only as a hash, tied to the address it was sent to. It works
for ten minutes and allows five tries; asking for a new one retires the old.

Making an account and signing in go through the same door. Asking for a code
says nothing about whether an account exists: an address with an account gets
a sign-in code, a new address on the sign-up screen gets a code that creates
the account once it is typed in, and a new address on the sign-in screen gets
an email saying there's no account yet — and every one of them answers "check
your email". No account row exists until the email is proven.

Too many codes or too many wrong guesses for one address pause it for fifteen
minutes (the "short break" screen).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from . import users

TTL = 10 * 60
TRIES = 5
RESEND_AFTER = 30
WINDOW = 15 * 60
SENDS_PER_WINDOW = 4     # the first code and three new ones
FAILS_PER_WINDOW = 10

SIGNUP, SIGNIN, NONE = "signup", "signin", "none"


def _digest(email: str, code: str) -> str:
    return hashlib.sha256(f"pearl.signin.v1|{email}|{code}".encode()).hexdigest()


def _paused(c, email: str, t: float, sending: bool = False) -> float:
    """Seconds left on a pause for this address, or 0.

    Wrong guesses pause both asking and answering; asking too often pauses
    only asking, so the code already sent still works."""
    rows = c.execute(
        "SELECT created_at, attempts FROM app_codes WHERE email = ? "
        "AND purpose IN ('signup', 'signin', 'none') AND created_at > ? "
        "ORDER BY created_at", (email, t - WINDOW)).fetchall()
    if (sending and len(rows) >= SENDS_PER_WINDOW) or \
            sum(int(r["attempts"]) for r in rows) >= FAILS_PER_WINDOW:
        return max(float(rows[0]["created_at"]) + WINDOW - t, 1.0)
    return 0.0


def start(base, email: str, first_name: str | None = None,
          creating: bool = False) -> dict:
    """Make a code for this address.

    Returns {"code", "purpose", "resend_in"} when one should be emailed,
    {"resend_in"} when the last one is too recent to replace, or
    {"paused": seconds}. `creating` is True on the sign-up screen.
    """
    email = users.normalise(email)
    t = users.now()
    with base.conn() as c:
        # Only a code still waiting to be used holds back a new one: once a
        # code has signed you in, the next sign-in needs a fresh one at once.
        last = c.execute(
            "SELECT created_at FROM app_codes WHERE email = ? AND used = 0 AND "
            "purpose IN ('signup', 'signin', 'none') ORDER BY created_at DESC",
            (email,)).fetchone()
        if last is not None and t - float(last["created_at"]) < RESEND_AFTER:
            return {"resend_in": int(RESEND_AFTER - (t - float(last["created_at"]))) + 1}
        paused = _paused(c, email, t, sending=True)
        if paused:
            return {"paused": int(paused)}
        account = users.by_email(base, email)
        purpose = SIGNIN if account else (SIGNUP if creating else NONE)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        c.execute("UPDATE app_codes SET used = 1 WHERE email = ? AND used = 0 "
                  "AND purpose IN ('signup', 'signin', 'none')", (email,))
        c.execute(
            "INSERT INTO app_codes (user_id, purpose, secret_hash, payload, "
            "expires_at, created_at, email) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account.id if account else 0, purpose, _digest(email, code),
             json.dumps({"first_name": users.clean_name(first_name)}),
             t + TTL, t, email))
    return {"code": code, "purpose": purpose, "resend_in": RESEND_AFTER}


def verify(base, email: str, code: str, owner: bool = False) -> dict:
    """Check a code.

    {"user": User, "created": bool} on success; otherwise {"error": "wrong",
    "left": n}, {"error": "expired"} or {"error": "paused", "paused": seconds}.
    `owner` makes a new account the owner (the first one on a deployment).
    """
    email = users.normalise(email)
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    t = users.now()
    with base.conn() as c:
        paused = _paused(c, email, t)
        if paused:
            return {"error": "paused", "paused": int(paused)}
        r = c.execute(
            "SELECT * FROM app_codes WHERE email = ? AND used = 0 AND purpose IN "
            "('signup', 'signin', 'none') ORDER BY created_at DESC",
            (email,)).fetchone()
        if r is None or float(r["expires_at"]) < t:
            return {"error": "expired"}
        if r["purpose"] == NONE or not hmac.compare_digest(
                r["secret_hash"], _digest(email, code)):
            tries = int(r["attempts"]) + 1
            c.execute("UPDATE app_codes SET attempts = ?, used = ? WHERE id = ?",
                      (tries, 1 if tries >= TRIES else 0, r["id"]))
            if tries >= TRIES:
                return {"error": "expired"}
            return {"error": "wrong", "left": TRIES - tries}
        c.execute("UPDATE app_codes SET used = 1 WHERE id = ?", (r["id"],))
        purpose = r["purpose"]
        try:
            first_name = json.loads(r["payload"] or "{}").get("first_name")
        except ValueError:
            first_name = None
    user = users.by_email(base, email)
    if user is not None:
        users.mark_verified(base, user.id)
        return {"user": users.by_id(base, user.id), "created": False}
    if purpose != SIGNUP:
        return {"error": "expired"}
    user = users.create_passwordless(base, email, first_name, owner=owner)
    if user is None:
        return {"error": "expired"}
    return {"user": user, "created": True}


def email_text(purpose: str, code: str, first_name: str | None, link: str) -> tuple[str, str]:
    """(subject, body) for a code email."""
    hello = f"Hi {first_name}," if first_name else "Hi,"
    if purpose == NONE:
        return ("Signing in to Pearl",
                f"{hello}\n\nSomeone asked to sign in to Pearl with this email, but "
                f"there's no Pearl account for it yet. To make one, go to {link}\n\n"
                "If that wasn't you, you can ignore this email.")
    what = "finish setting up Pearl" if purpose == SIGNUP else "sign in to Pearl"
    return (f"Your Pearl code: {code}",
            f"{hello}\n\nYour code to {what} is:\n\n    {code}\n\n"
            "It works for 10 minutes. If you didn't ask for it, ignore this "
            "email — nobody can get in without the code.")
