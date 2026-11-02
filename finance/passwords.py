"""What makes a password strong enough (THL-114, Oct 31).

Three rules, each shown as it's met on sign-up (O-02) and on a new password
(A-07, S-02), and checked again here whatever the screen said:

* at least 12 characters;
* not a common or leaked password;
* doesn't contain her email (Pearl doesn't ask for her name).

No rules about symbols or numbers (NIST 800-63B): length does the work, and
pasting or a password manager's suggestion is welcome.

"Leaked" means on Have I Been Pwned's list, asked by k-anonymity: only the
first five characters of the password's SHA-1 leave the server. That call is
made where it's turned on (hosted, or `PEARL_PWNED_CHECK=1`); anywhere else,
and if the service doesn't answer in time, the short list of common
passwords below still applies.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from functools import lru_cache

MIN_LENGTH = 12
PWNED_ENV = "PEARL_PWNED_CHECK"
PWNED_URL = "https://api.pwnedpasswords.com/range/"
PWNED_TIMEOUT = 2.0

# Words and runs that make up most guessed passwords; a password that is one
# of these, with digits or symbols around it, is common however long it is.
_COMMON_WORDS = {
    "password", "passw0rd", "qwerty", "qwertyuiop", "asdfgh", "asdfghjkl", "zxcvbnm",
    "letmein", "welcome", "iloveyou", "admin", "administrator", "login", "master",
    "monkey", "dragon", "football", "baseball", "hockey", "soccer", "sunshine",
    "princess", "shadow", "superman", "batman", "trustno1", "starwars", "freedom",
    "whatever", "computer", "internet", "changeme", "secret", "pearl", "money",
    "canada", "toronto", "maplesyrup", "abc", "abcdef", "abcdefgh", "abcdefghijkl",
    "qazwsx", "1q2w3e4r", "1qaz2wsx", "zaq12wsx", "default", "access", "hello",
    "helloworld", "michael", "jennifer", "jordan", "summer", "winter", "autumn",
    "spring", "loveyou", "fuckyou", "pokemon", "minecraft", "test", "testing",
}
_SEQUENCES = ("0123456789", "1234567890", "9876543210", "abcdefghijklmnopqrstuvwxyz",
              "qwertyuiopasdfghjklzxcvbnm")


def _common(password: str) -> bool:
    p = password.lower()
    if len(set(p)) <= 2:                              # "aaaaaaaaaaaa", "abababababab"
        return True
    if any(p in s * 3 or p in (s * 3)[::-1] for s in _SEQUENCES):   # "123456789012"
        return True
    core = re.sub(r"[^a-z]", "", p)
    if not core:                                      # all digits and symbols
        return len(set(p)) <= 4
    return core in _COMMON_WORDS


def pwned_check_on(hosted: bool = False) -> bool:
    value = os.environ.get(PWNED_ENV, "").strip()
    if value in ("0", "false", "no"):
        return False
    return hosted or value in ("1", "true", "yes")


@lru_cache(maxsize=512)
def _range(prefix: str) -> frozenset[str]:
    req = urllib.request.Request(PWNED_URL + prefix, headers={
        "User-Agent": "Pearl password check", "Add-Padding": "true"})
    with urllib.request.urlopen(req, timeout=PWNED_TIMEOUT) as resp:   # noqa: S310
        body = resp.read().decode("utf-8", "replace")
    return frozenset(line.split(":", 1)[0].strip().upper() for line in body.splitlines()
                     if ":" in line and not line.rstrip().endswith(":0"))


def leaked(password: str) -> bool:
    """On Have I Been Pwned's list. False when the service can't be asked."""
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()   # noqa: S324
    try:
        return digest[5:] in _range(digest[:5])
    except Exception:                                  # noqa: BLE001
        return False


def _contains_email(password: str, email: str | None) -> bool:
    email = (email or "").strip().lower()
    if not email:
        return False
    p = password.lower()
    local = email.split("@", 1)[0]
    return email in p or (len(local) >= 3 and local in p)


def rules(password: str, email: str | None = None, remote: bool = False) -> dict:
    """Each rule, met or not, and what the strength meter shows.

    {"length": bool, "common": bool, "email": bool, "more": n, "ok": bool,
     "segments": 1-4, "label": "Too short" | "Weak" | "Fair" | "Good" | "Strong"}
    `common` and `email` are True when the password passes them.
    """
    password = str(password or "")
    length = len(password) >= MIN_LENGTH
    common = not _common(password) and not (remote and length and leaked(password))
    mail = not _contains_email(password, email)
    ok = length and common and mail
    if not length:
        segments, label = 1, "Too short"
    elif not (common and mail):
        segments, label = 1, "Weak"
    else:
        kinds = sum(bool(re.search(pattern, password))
                    for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
        segments = 2 + (len(password) >= 16) + (kinds >= 3 or len(password) >= 20)
        segments = min(segments, 4)
        label = {2: "Fair", 3: "Good", 4: "Strong"}[segments]
    return {"length": length, "common": common, "email": mail,
            "more": max(MIN_LENGTH - len(password), 0), "ok": ok,
            "segments": segments, "label": label}


def problem(password: str, email: str | None = None, remote: bool = False) -> str | None:
    """What's wrong with a new password, in words, or None."""
    r = rules(password, email, remote)
    if not r["length"]:
        return f"Passwords need at least {MIN_LENGTH} characters."
    if not r["common"]:
        return "That password is too common, or it has been leaked. Choose another."
    if not r["email"]:
        return "Choose a password that doesn't include your email."
    return None
