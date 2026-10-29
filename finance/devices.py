"""New devices: confirming it's her when someone signs in somewhere new
(Pearl THL-114 A-07, A-08), and the recovery codes that stand in when her
other device isn't to hand.

A browser she signs in on is remembered by a cookie holding a random token;
only its hash is kept here, with when it was last used. A passkey proves the
device by itself, so signing in with one trusts the browser straight away, as
does making an account. An email code proves only the inbox, so when the
account already has another trusted device, a code sign-in on a new browser
waits until that device approves it (A-08), or a recovery code is typed in.
An account with no other device signs in as before: there is nothing to ask.

Once confirmed, a browser is trusted for 30 days from when it was last used.

An approval asked for lasts five minutes. "This wasn't me" on the other device
refuses it, and Pearl emails her a security notice.

Recovery codes are ten, made together, shown once and kept only as hashes in
`app_codes`; making new ones retires the old. Each works once.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from urllib.parse import unquote

from . import users

COOKIE = "pearl_device"
TRUST_DAYS = 30
APPROVAL_TTL = 5 * 60
RECOVERY_COUNT = 10
# A recovery code never expires; app_codes wants a time, so it gets a far one.
_NEVER = 10 ** 12
# No 0/O, 1/I/L: a code copied from paper should type in as written.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _hash(token: str) -> str:
    return hashlib.sha256(f"pearl.device.v1|{token}".encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


# ── What to call a device ───────────────────────────────────────────────────

def label_from(user_agent: str | None) -> str:
    """"Chrome on Mac", "Safari on iPhone" — enough to recognise it by."""
    ua = user_agent or ""
    if "iPhone" in ua:
        system = "iPhone"
    elif "iPad" in ua:
        system = "iPad"
    elif "Android" in ua:
        system = "Android"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        system = "Mac"
    elif "Windows" in ua:
        system = "Windows"
    elif "Linux" in ua:
        system = "Linux"
    else:
        system = ""
    # Pearl's iPhone app (2026-10-29) names itself: "PearlApp/1.0 (iPhone; iOS 17.4)".
    if "PearlApp/" in ua:
        browser = "Pearl app"
    elif "Edg/" in ua:
        browser = "Edge"
    elif "Firefox/" in ua or "FxiOS" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "A browser"
    return f"{browser} on {system}" if system else browser


def near_from(headers) -> str | None:
    """"Toronto, ON", from the host's location headers when it sends them
    (Vercel does); otherwise nothing, rather than a guess."""
    city = unquote(headers.get("X-Vercel-IP-City", "") or "").strip()
    region = (headers.get("X-Vercel-IP-Country-Region", "") or "").strip()
    if not city:
        return None
    return f"{city}, {region}" if region else city


# ── Trusted devices ─────────────────────────────────────────────────────────

def _row(base, token: str | None) -> dict | None:
    if not token:
        return None
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_devices WHERE id = ?", (_hash(token),)).fetchone()
    return dict(r) if r else None


def trusted(base, user_id: int, token: str | None) -> bool:
    r = _row(base, token)
    return bool(r and int(r["user_id"]) == int(user_id)
                and float(r["trusted_until"]) > users.now())


def trust(base, user_id: int, token: str, label: str) -> None:
    """Remember this browser for her, for 30 days from now."""
    t = users.now()
    until = t + TRUST_DAYS * 86400
    with base.conn() as c:
        c.execute("DELETE FROM app_devices WHERE id = ?", (_hash(token),))
        c.execute("DELETE FROM app_devices_removed WHERE id = ? AND user_id = ?",
                  (_hash(token), int(user_id)))
        c.execute("INSERT INTO app_devices (id, user_id, label, trusted_until, created_at, "
                  "last_used_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (_hash(token), int(user_id), label, until, t, t))


def touch(base, user_id: int, token: str | None) -> None:
    """A trusted browser in use stays trusted: another 30 days from now."""
    t = users.now()
    with base.conn() as c:
        c.execute("UPDATE app_devices SET trusted_until = ?, last_used_at = ? "
                  "WHERE id = ? AND user_id = ? AND trusted_until > ?",
                  (t + TRUST_DAYS * 86400, t, _hash(token or ""), int(user_id), t))


def others(base, user_id: int, token: str | None) -> list[dict]:
    """Her other trusted devices, the one used most recently first."""
    mine = _hash(token) if token else ""
    with base.conn() as c:
        rows = c.execute("SELECT * FROM app_devices WHERE user_id = ? AND trusted_until > ? "
                         "AND id != ? ORDER BY last_used_at DESC",
                         (int(user_id), users.now(), mine)).fetchall()
    return [dict(r) for r in rows]


def hashed(token: str | None) -> str:
    """The stored id of a browser's token (its row in app_devices)."""
    return _hash(token) if token else ""


def mine(base, user_id: int, token: str | None) -> list[dict]:
    """Profile › Sign-in and security (2026-10-26): every browser trusted for
    her, this one first, then the most recently used. `id` is the stored
    hash, never the token itself."""
    here = hashed(token)
    with base.conn() as c:
        rows = c.execute("SELECT id, label, last_used_at, created_at FROM app_devices "
                         "WHERE user_id = ? AND trusted_until > ? ORDER BY last_used_at DESC",
                         (int(user_id), users.now())).fetchall()
    out = [{**dict(r), "this": r["id"] == here} for r in rows]
    return sorted(out, key=lambda d: not d["this"])


def forget(base, user_id: int, device_id: str) -> bool:
    """Stop trusting one of her browsers: it's signed out on its next
    request, and never asked to approve a sign-in again."""
    with base.conn() as c:
        cur = c.execute("DELETE FROM app_devices WHERE id = ? AND user_id = ?",
                        (str(device_id or ""), int(user_id)))
        if cur.rowcount <= 0:
            return False
        c.execute("DELETE FROM app_devices_removed WHERE id = ? AND user_id = ?",
                  (str(device_id), int(user_id)))
        c.execute("INSERT INTO app_devices_removed (id, user_id, removed_at) VALUES (?, ?, ?)",
                  (str(device_id), int(user_id), users.now()))
        return True


def still_hers(base, user_id: int, device_id: str) -> bool:
    """False once she removed this browser from her devices."""
    with base.conn() as c:
        r = c.execute("SELECT 1 FROM app_devices_removed WHERE id = ? AND user_id = ?",
                      (str(device_id or ""), int(user_id))).fetchone()
    return r is None


def needs_check(base, user_id: int, token: str | None) -> bool:
    """A-07: a browser she hasn't confirmed, on an account that has one."""
    return not trusted(base, user_id, token) and bool(others(base, user_id, token))


def choices(base, user_id: int, token: str | None) -> dict:
    """What A-07 can offer: the device to approve on, and recovery codes."""
    device = others(base, user_id, token)[0]
    return {"approve": {"label": device["label"], "used_at": device["last_used_at"]},
            "recovery": recovery_left(base, user_id) > 0}


# ── Approving from another device (A-08) ────────────────────────────────────

def ask(base, user_id: int, label: str, near: str | None) -> tuple[int, str]:
    """A new approval for her other devices to answer: (id, secret). The
    secret stays with the browser that asked, so only it can collect."""
    secret = secrets.token_urlsafe(24)
    t = users.now()
    with base.conn() as c:
        # One question at a time from her account.
        c.execute("UPDATE app_device_approvals SET state = 'replaced' "
                  "WHERE user_id = ? AND state = 'pending'", (int(user_id),))
        sql = ("INSERT INTO app_device_approvals (user_id, secret_hash, label, near, state, "
               "created_at, expires_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)")
        args = (int(user_id), _hash(secret), label, near, t, t + APPROVAL_TTL)
        # As Store.add_fixed_cost: Postgres has no lastrowid.
        if getattr(base, "is_postgres", False):
            approval_id = int(c.execute(sql + " RETURNING id", args).fetchone()["id"])
        else:
            approval_id = int(c.execute(sql, args).lastrowid)
    return approval_id, secret


def state(base, approval_id: int, secret: str) -> str:
    """pending, approved, denied, expired, or gone (not hers to ask about)."""
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_device_approvals WHERE id = ?",
                      (int(approval_id),)).fetchone()
    if r is None or not hmac.compare_digest(r["secret_hash"], _hash(secret or "")):
        return "gone"
    if r["state"] == "pending" and float(r["expires_at"]) <= users.now():
        return "expired"
    return r["state"] if r["state"] in ("pending", "approved", "denied") else "gone"


def finish(base, approval_id: int) -> None:
    """Collected: an approval signs in once."""
    with base.conn() as c:
        c.execute("UPDATE app_device_approvals SET state = 'used' WHERE id = ?",
                  (int(approval_id),))


def waiting(base, user_id: int) -> list[dict]:
    """What her signed-in devices are being asked to approve."""
    with base.conn() as c:
        rows = c.execute("SELECT id, label, near, created_at FROM app_device_approvals "
                         "WHERE user_id = ? AND state = 'pending' AND expires_at > ? "
                         "ORDER BY created_at DESC", (int(user_id), users.now())).fetchall()
    return [dict(r) for r in rows]


def answer(base, user_id: int, approval_id: int, approve: bool) -> dict | None:
    """Her answer from a trusted device, or None when there's nothing to
    answer (another account's, already answered, or expired)."""
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_device_approvals WHERE id = ? AND user_id = ? "
                      "AND state = 'pending' AND expires_at > ?",
                      (int(approval_id), int(user_id), users.now())).fetchone()
        if r is None:
            return None
        c.execute("UPDATE app_device_approvals SET state = ? WHERE id = ?",
                  ("approved" if approve else "denied", int(approval_id)))
    return dict(r)


# ── Recovery codes ──────────────────────────────────────────────────────────

def _clean(code: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(code or "").upper())


def _code_hash(user_id: int, code: str) -> str:
    return hashlib.sha256(f"pearl.recovery.v1|{int(user_id)}|{_clean(code)}".encode()).hexdigest()


def make_recovery_codes(base, user_id: int) -> list[str]:
    """Ten new codes, "ABCD-EFGH", replacing any she had."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    t = users.now()
    with base.conn() as c:
        c.execute("DELETE FROM app_codes WHERE user_id = ? AND purpose = 'recovery'",
                  (int(user_id),))
        for code in codes:
            c.execute("INSERT INTO app_codes (user_id, purpose, secret_hash, expires_at, "
                      "created_at) VALUES (?, 'recovery', ?, ?, ?)",
                      (int(user_id), _code_hash(user_id, code), _NEVER, t))
    return codes


def recovery_left(base, user_id: int) -> int:
    with base.conn() as c:
        r = c.execute("SELECT COUNT(*) AS n FROM app_codes WHERE user_id = ? "
                      "AND purpose = 'recovery' AND used = 0", (int(user_id),)).fetchone()
    return int(r["n"])


def use_recovery(base, user_id: int, code: str) -> bool:
    """True, and the code is spent, when it's one of hers not yet used."""
    with base.conn() as c:
        r = c.execute("SELECT id FROM app_codes WHERE user_id = ? AND purpose = 'recovery' "
                      "AND used = 0 AND secret_hash = ?",
                      (int(user_id), _code_hash(user_id, code))).fetchone()
        if r is None:
            return False
        c.execute("UPDATE app_codes SET used = 1 WHERE id = ?", (r["id"],))
    return True
