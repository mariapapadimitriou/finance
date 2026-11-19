"""Tidy names (TEST-46, product owner 2026-11-19): what a row is called,
cleaned for display only. Rule-based, never a list of merchants.

* A payroll prefix goes: "Direct Deposit Payroll Acme" → "Acme".
* A trailing city goes only when the bank's own location for that row
  names it: "Bar Isabel Toronto" with city "Toronto" → "Bar Isabel".
* Her own renames always win (callers check them first; `display` takes
  them). Stored merchants, merchant keys and rules are never changed.
"""

from __future__ import annotations

# Words a bank puts in front of pay. Only dropped as a leading run that
# says payroll or direct deposit, and never the whole name.
_PAY_WORDS = {"direct", "dir", "deposit", "dep", "payroll", "pay", "dd", "-", "from"}


def _payroll_prefix(words: list[str]) -> int:
    """How many leading words are a payroll prefix (0 for none)."""
    n = 0
    while n < len(words) and words[n].lower().strip(":") in _PAY_WORDS:
        n += 1
    lead = {w.lower().strip(":") for w in words[:n]}
    says_pay = "payroll" in lead or ({"direct", "dir"} & lead and {"deposit", "dep"} & lead)
    return n if says_pay and n < len(words) else 0


def tidy(name: str | None, city: str | None = None) -> str:
    """The name to show for a bank's merchant name and that row's city."""
    words = " ".join(str(name or "").split()).split(" ")
    if not words or words == [""]:
        return ""
    words = words[_payroll_prefix(words):]
    town = " ".join(str(city or "").split()).split(" ") if city and str(city).strip() else []
    if town and len(words) > len(town) and [w.lower() for w in words[-len(town):]] == [w.lower() for w in town]:
        words = words[:-len(town)]
    return " ".join(words)


def of(t) -> str:
    """A transaction's tidy name, from its merchant and the bank's city."""
    return tidy(t.merchant or t.description, ((t.raw or {}).get("city") if t is not None else None))


def display(t, names: dict | None = None) -> str:
    """Her name for it when she renamed the merchant, else the tidy name."""
    if t is None:
        return ""
    if names:
        key = " ".join((t.merchant or "").lower().split())
        if names.get(key):
            return names[key]
    return of(t) or t.merchant or t.description or ""
