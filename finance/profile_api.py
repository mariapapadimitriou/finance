"""Profile: the accounts page, how each account counts, balances added by
hand, removing an account, and the saved sorting rules.

Pearl Handoff, page "Accounts & settings": S-01 (the hub's counts), S-03
(Categories and rules), AM-01 to AM-07 and C-01 / C-06 (Accounts).

How an account counts is one decision, "Count in my budget", recorded beside
the account rather than on its rows (`account_settings.counted`). An account
left out keeps syncing — its transactions stay in Pearl — but every row on it
loads as excluded, so `analytics.counts_as_spending` (the one gate for
spending) and everything that reads income or the snapshot leave it out
without having to know. Its balance leaves the position, the debts and the
Anchor too.

An account the bank handed over that was never synced (switched off under the
old Sync switch) reads as not counted; counting it switches syncing on and
fetches its history.
"""

from __future__ import annotations

import json
import re
from datetime import date

from flask import jsonify, request

from .api import (_account_rows, _anchor_accounts, _home_sts, _json_setting,
                  _reclassify, _today_iso, _txlist_rows, bp, store)

_MASK = re.compile(r"\s*(?:••|\*{2,}|x{2,})\s*\d{2,4}\s*$", re.I)
_SAVINGS = {"savings", "money market", "hsa", "cash management", "hisa", "tfsa savings"}
SHARE_MIN, SHARE_MAX = 1, 99


def _kind(row: dict) -> str:
    """card, savings, chequing, loan, investment or account."""
    ptype = (row.get("plaid_type") or "").lower()
    sub = (row.get("plaid_subtype") or "").lower()
    if ptype == "credit" or row.get("is_card"):
        return "card"
    if ptype == "loan":
        return "loan"
    if row.get("kind_label") == "Investment" or ptype in ("investment", "brokerage"):
        return "investment"
    if sub in _SAVINGS:
        return "savings"
    if ptype == "depository" or sub in ("checking", "chequing"):
        return "chequing"
    return "account"


def _base_name(name: str) -> str:
    return _MASK.sub("", name or "").strip() or "Account"


def _safe_to_spend(st) -> float | None:
    """Safe to spend this month as Home shows it, for the toast (AM-03)."""
    try:
        today = date.fromisoformat(_today_iso())
        sts = _home_sts(st, st.all_transactions(), today)
    except Exception:                                    # noqa: BLE001
        return None
    if sts.get("state") != "ok" or sts.get("amount") is None:
        return None
    return sts.get("shown", sts["amount"])


def _anchor_ids(st) -> set[str]:
    return set(_json_setting(st, "anchor_accounts", []))


def _set_anchor(st, account_id: str, on: bool) -> None:
    ids = _anchor_ids(st)
    ids = (ids | {account_id}) if on else (ids - {account_id})
    st.set_setting("anchor_accounts", json.dumps(sorted(ids)))


def _linked_rows(st) -> list[dict]:
    """Every account with rows or a bank behind it, as the Accounts page
    lists it. Accounts removed with their history kept are left out."""
    from . import milestones
    items = {i["item_id"]: i for i in st.plaid_items()}
    anchor = _anchor_ids(st)
    anchorable = {a["account_id"] for a in _anchor_accounts(st)}
    out = []
    for row in _account_rows(st):
        if row.get("removed"):
            continue
        aid = row["account_id"]
        plaid = row.get("source") == "plaid"
        item = items.get(row.get("item_id") or "")
        state = milestones.connection_state(item) if item else None
        if plaid and not item:
            state = "disconnected"
        kind = _kind(row)
        counted = bool(row.get("counted", True)) and row.get("syncs") is not False
        joint = bool(row.get("joint"))
        if not plaid:
            status = "manual"
        elif state == "needs_sign_in":
            status = "sign_in"
        elif state == "bank_down":
            status = "retrying"
        elif state == "disconnected":
            status = "disconnected"
        elif kind == "investment":
            # Balance only: Plaid's Transactions product doesn't carry its
            # activity, and money moved into it is Saved, never spending.
            status = "investment"
        elif not counted:
            status = "not_counted"
        elif joint:
            status = "joint"
        else:
            status = "up_to_date"
        balance = row.get("balance") or {}
        updated = (item or {}).get("last_synced") or balance.get("as_of")
        out.append({
            "id": aid,
            "name": row.get("nickname") or _base_name(row.get("account_name") or aid),
            "bank_name": _base_name(row.get("account_name") or aid),
            "nickname": row.get("nickname") or "",
            "mask": row.get("mask") or "",
            "institution": row.get("institution") or "",
            "logo": (item or {}).get("logo") or "",
            "kind": kind,
            "source": "plaid" if plaid else "statement",
            "status": status,
            "counted": counted,
            "syncs": row.get("syncs"),
            "joint": joint,
            "joint_share": row.get("joint_share"),
            "joint_people": row.get("joint_people") or [],
            "anchor": aid in anchor,
            "can_anchor": kind == "savings" and aid in anchorable,
            "balance": balance.get("current"),
            "owing": kind in ("card", "loan"),
            "updated_at": updated,
            "disconnected_on": (((updated or "")[:10] or None)
                                if state == "disconnected" else None),
            "history_from": row.get("first_date"),
            "transactions": row.get("transactions") or 0,
            "item_id": row.get("item_id") or "",
        })
    rank = {"card": 1, "loan": 2, "investment": 3}
    out.sort(key=lambda a: (a["source"] != "plaid", a["institution"].lower(),
                            rank.get(a["kind"], 0), a["name"].lower()))
    return out


def _hand_rows(st) -> list[dict]:
    anchor = _anchor_ids(st)
    return [{
        "id": m["account_id"], "name": m["name"], "bank_name": m["name"], "nickname": "",
        # The last four digits she gave it (2026-10-14): a transfer naming
        # them is Saved, like one to an investment account Plaid pulled in.
        "mask": m.get("last4") or "", "institution": "", "logo": "",
        "kind": "card" if m["kind"] == "credit" else m["kind"],
        "source": "hand", "status": "manual", "counted": m["counted"], "syncs": None,
        "joint": False, "joint_share": None, "joint_people": [],
        "anchor": m["account_id"] in anchor,
        "can_anchor": m["kind"] == "savings", "balance": m["balance"],
        "owing": m["kind"] == "credit", "updated_at": m["updated_on"],
        "disconnected_on": None, "history_from": None, "transactions": 0, "item_id": "",
    } for m in st.manual_accounts()]


def _last4(value) -> str | None:
    """Four digits, or "" for none; None when it isn't four digits."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return digits[-4:] if len(digits) >= 4 else None


def _all_rows(st) -> list[dict]:
    return _linked_rows(st) + _hand_rows(st)


def _find(st, account_id: str) -> dict | None:
    return next((a for a in _all_rows(st) if a["id"] == account_id), None)


NEEDS_YOU = {"sign_in", "disconnected"}


@bp.get("/accounts/overview")
def accounts_overview():
    """AM-01 / C-01: linked accounts, those added by hand, and what needs her."""
    from . import plaid_link, secrets_box
    from .analytics import currency_mix
    st = store()
    rows = _all_rows(st)
    return jsonify({
        "linked": [a for a in rows if a["source"] == "plaid"],
        "added": [a for a in rows if a["source"] != "plaid"],
        "needs_you": sum(1 for a in rows if a["status"] in NEEDS_YOU),
        "plaid": {"configured": plaid_link.configured(),
                  "environment": plaid_link.environment(),
                  "encryption_ready": secrets_box.available()},
        "currency_mix": currency_mix(st.all_transactions()),
    })


@bp.put("/accounts/<path:account_id>/settings")
def account_settings(account_id: str):
    """How one account counts (AM-02 to AM-04, AM-06): `counted`,
    `joint_share` (1–99, or null for not joint), `anchor` and `nickname`.

    Answers with the account as listed and safe to spend afterwards, so the
    page can say what changed (AM-03)."""
    st = store()
    account = _find(st, account_id)
    if account is None:
        return jsonify({"error": "No such account."}), 404
    body = request.get_json(silent=True) or {}
    hand = account["source"] == "hand"
    resync = False
    reclassify = False

    if "nickname" in body:
        if hand:
            name = " ".join(str(body.get("nickname") or "").split())[:40]
            if not name:
                return jsonify({"error": "Give it a name."}), 400
            st.update_manual_account(account_id, name=name)
        else:
            nickname = " ".join(str(body.get("nickname") or "").split())[:40]
            st.set_account_setting(account_id, nickname=nickname)

    if "last4" in body:
        if not hand or account["kind"] not in ("savings", "investment"):
            return jsonify({"error": "Digits go on a savings or investment account you "
                                     "added by hand."}), 400
        last4 = _last4(body.get("last4"))
        if last4 is None:
            return jsonify({"error": "The last four digits, like 3333."}), 400
        st.update_manual_account(account_id, last4=last4 or None)
        reclassify = True

    if "joint_share" in body:
        if hand:
            return jsonify({"error": "Only a linked account can be joint."}), 400
        share = body.get("joint_share")
        if share == "auto":
            # AM-08: joint, with the share worked out from what each puts in.
            st.clear_joint_share(account_id)
            reclassify = True
        else:
            if share is not None:
                try:
                    share = float(share)
                except (TypeError, ValueError):
                    share = -1
                if not (SHARE_MIN <= share <= SHARE_MAX):
                    return jsonify({"error": "Enter a share between 1% and 99%."}), 400
                share = round(share, 2)
            st.set_joint_share(account_id, share)
            reclassify = True

    if "joint_people" in body:
        if hand:
            return jsonify({"error": "Only a linked account can be joint."}), 400
        raw = body.get("joint_people")
        if not isinstance(raw, list):
            return jsonify({"error": "Name the people you share it with."}), 400
        people = []
        for p in raw:
            name = " ".join(str(p or "").split())[:40]
            if name and name.lower() not in {x.lower() for x in people}:
                people.append(name)
        if not people:
            return jsonify({"error": "Name at least one person you share it with."}), 400
        st.set_joint_people(account_id, people[:6])
        reclassify = True

    if "anchor" in body:
        on = bool(body.get("anchor"))
        if on and not account["can_anchor"]:
            return jsonify({"error": "Only a savings account can count toward your "
                                     "Anchor."}), 400
        _set_anchor(st, account_id, on)

    if "counted" in body and account["kind"] == "investment":
        return jsonify({"error": "Spending doesn’t happen from an investment account, so it "
                                 "isn’t counted in your budget."}), 400
    if "counted" in body:
        on = bool(body.get("counted"))
        if hand:
            st.update_manual_account(account_id, counted=on)
        else:
            st.set_account_setting(account_id, counted=on)
            rules = st.account_sync_rules()
            rule = rules.get(account_id)
            if on and rule and not rule["enabled"]:
                # Never synced: counting it means bringing it in.
                st.set_account_sync(account_id, True, name=rule["account_name"],
                                    item_id=rule["item_id"])
                if rule["item_id"]:
                    st.rewind_plaid_cursor(rule["item_id"])
                    resync = True
            reclassify = True

    if reclassify:
        _reclassify(st)
    return jsonify({"ok": True, "account": _find(st, account_id),
                    "safe_to_spend": _safe_to_spend(st), "resync": resync})


def _parse_balance(value) -> float | None:
    from .models import parse_amount
    n = parse_amount(value)
    if n is None or n != n or abs(n) > 1e9:
        return None
    return round(abs(n), 2)


@bp.post("/accounts/manual")
def add_manual_account():
    """AM-05: a balance for a bank Pearl can't link."""
    st = store()
    body = request.get_json(silent=True) or {}
    name = " ".join(str(body.get("name") or "").split())[:40]
    kind = str(body.get("kind") or "")
    balance = _parse_balance(body.get("balance"))
    if not name:
        return jsonify({"error": "Give it a name, like the bank and account.",
                        "field": "name"}), 400
    if kind not in st.MANUAL_KINDS:
        return jsonify({"error": "Choose what kind of account it is.", "field": "kind"}), 400
    if balance is None:
        return jsonify({"error": "Enter the balance today, like 3,000.",
                        "field": "balance"}), 400
    last4 = _last4(body.get("last4"))
    if last4 is None:
        return jsonify({"error": "The last four digits, like 3333.", "field": "last4"}), 400
    account_id = st.add_manual_account(name, kind, balance, _today_iso(),
                                       last4 if kind in ("savings", "investment") else "")
    if last4:
        _reclassify(st)
    return jsonify({"ok": True, "account": _find(st, account_id)}), 201


@bp.put("/accounts/<path:account_id>/balance")
def update_manual_balance(account_id: str):
    """AM-06 "Update balance": what a hand-added account holds today."""
    st = store()
    if st.manual_account(account_id) is None:
        return jsonify({"error": "Only a balance you added can be updated here."}), 404
    balance = _parse_balance((request.get_json(silent=True) or {}).get("balance"))
    if balance is None:
        return jsonify({"error": "Enter the balance today, like 3,000."}), 400
    st.update_manual_account(account_id, balance=balance, updated_on=_today_iso())
    return jsonify({"ok": True, "account": _find(st, account_id)})


@bp.post("/accounts/<path:account_id>/remove")
def remove_account(account_id: str):
    """AM-07: stop syncing an account and disconnect it, keeping its past
    transactions (`transactions: "keep"`) or deleting them too ("delete").

    Plaid disconnects a whole bank login, not one account, so the login is
    disconnected once no other account on it is still listed."""
    from . import plaid_link
    st = store()
    account = _find(st, account_id)
    if account is None:
        return jsonify({"error": "No such account."}), 404
    what = (request.get_json(silent=True) or {}).get("transactions", "keep")
    if what not in ("keep", "delete"):
        return jsonify({"error": "Say whether to keep its transactions or delete them."}), 400
    _set_anchor(st, account_id, False)
    if account["source"] == "hand":
        st.delete_manual_account(account_id)
        return jsonify({"ok": True, "removed": 0, "disconnected": False})

    deleted = st.clear_transactions(account_id) if what == "delete" else 0
    rules = st.account_sync_rules()
    rule = rules.get(account_id)
    if rule:
        st.set_account_sync(account_id, False, name=rule["account_name"],
                            item_id=rule["item_id"])
    st.set_account_setting(account_id, removed=True)
    st.set_joint_share(account_id, None)
    disconnected = False
    item_id = account["item_id"]
    if item_id:
        still = [a for a in _linked_rows(st) if a["item_id"] == item_id]
        if not still and any(i["item_id"] == item_id for i in st.plaid_items()):
            plaid_link.unlink(st, item_id)
            disconnected = True
    _reclassify(st)
    return jsonify({"ok": True, "removed": deleted, "disconnected": disconnected})


@bp.post("/accounts/<path:account_id>/merge")
def merge_account(account_id: str):
    """"Same account as…": merge this account into another one (`into`),
    for two copies of one card the automatic check didn't recognise. See
    finance/merge.py. The kept account keeps its own settings, and takes this
    one's joint share, nickname and Anchor where it has none."""
    from . import merge, plaid_link
    st = store()
    into_id = str((request.get_json(silent=True) or {}).get("into") or "")
    account, into = _find(st, account_id), _find(st, into_id)
    if account is None or into is None or account_id == into_id:
        return jsonify({"error": "Choose the other account to keep."}), 404
    if "hand" in (account["source"], into["source"]):
        return jsonify({"error": "An account you added by hand has no transactions to merge."}), 400
    if account["kind"] != into["kind"]:
        return jsonify({"error": "Only the same kind of account can be merged."}), 400
    out = merge.merge(st, account_id, into_id)
    if account["joint"] and not into["joint"]:
        st.set_joint(into_id, (st.joint_accounts() or {}).get(account_id) or "Joint")
        if account["joint_share"] is not None:
            st.set_joint_share(into_id, account["joint_share"])
    if account["nickname"] and not into["nickname"]:
        st.set_account_setting(into_id, nickname=account["nickname"])
    if account["anchor"]:
        _set_anchor(st, account_id, False)
        _set_anchor(st, into_id, True)
    # The copy goes: no more syncing, off the list, and a connection with
    # nothing else listed is disconnected (as AM-07 does).
    rule = st.account_sync_rules().get(account_id)
    if rule:
        st.set_account_sync(account_id, False, name=rule["account_name"], item_id=rule["item_id"])
    st.set_account_setting(account_id, removed=True)
    st.set_joint_share(account_id, None)
    item_id = account["item_id"]
    if item_id and item_id != into["item_id"]:
        still = [a for a in _linked_rows(st) if a["item_id"] == item_id]
        if not still and any(i["item_id"] == item_id for i in st.plaid_items()):
            plaid_link.unlink(st, item_id)
    _reclassify(st)
    return jsonify({"ok": True, **out, "account": _find(st, into_id)})


@bp.post("/accounts/<path:account_id>/keep-as-manual")
def keep_as_manual(account_id: str):
    """C-06 "Keep it as a manual account": a disconnected account becomes a
    balance added by hand, at its last known balance. Its past transactions
    stay in Pearl."""
    st = store()
    account = _find(st, account_id)
    if account is None or account["source"] != "plaid":
        return jsonify({"error": "No such linked account."}), 404
    kind = {"card": "credit", "savings": "savings"}.get(account["kind"], "chequing")
    new_id = st.add_manual_account(
        account["name"], kind, round(abs(account["balance"] or 0.0), 2),
        (account["updated_at"] or _today_iso())[:10])
    if account["anchor"]:
        _set_anchor(st, account_id, False)
        if kind == "savings":
            _set_anchor(st, new_id, True)
    rule = st.account_sync_rules().get(account_id)
    if rule:
        st.set_account_sync(account_id, False, name=rule["account_name"],
                            item_id=rule["item_id"])
    st.set_account_setting(account_id, removed=True)
    return jsonify({"ok": True, "account": _find(st, new_id)})


# ── S-01: the hub's counts ───────────────────────────────────────────────

@bp.get("/profile")
def profile_summary():
    st = store()
    rows = _all_rows(st)
    from .projections_api import _report
    return jsonify({"accounts": len(rows),
                    "needs_you": sum(1 for a in rows if a["status"] in NEEDS_YOU),
                    "rules": len(_rules(st)),
                    # "Opened an investing account?" (GR-37), which says it
                    # can be undone here.
                    "investing": _report(st)})


# ── S-03: Categories and rules ───────────────────────────────────────────

def _merchant_names(st) -> dict[str, str]:
    names: dict[str, str] = {}
    for t in st.all_transactions():
        names.setdefault((t.merchant or "").strip().lower(), t.merchant)
    return names


def _exclusion_name(r: dict, accounts: dict[str, str]) -> str:
    parts = [p for p in (r.get("keyword"), r.get("counterparty")) if p]
    if parts:
        text = " · ".join(parts)
        return text[:1].upper() + text[1:]
    if r.get("account_id"):
        return accounts.get(r["account_id"], "An account")
    return r.get("reason") or "Left out"


def _rules(st) -> list[dict]:
    """Her saved rules, newest kinds last: merchants, transfer destinations,
    then what she leaves out."""
    names = _merchant_names(st)
    out = []
    for key, category in sorted(st.overrides().items()):
        if key.startswith("entity:"):
            continue
        out.append({"id": f"merchant:{key}", "kind": "merchant",
                    "name": names.get(key) or key.title(), "category": category})
    labels = st.destination_labels()
    for key, category in sorted(st.destinations().items()):
        label = labels.get(key) or key.split(":", 1)[-1].title()
        name = (f"Transfers to {label}" if key.startswith(("to:", "acct:")) else label)
        out.append({"id": f"destination:{key}", "kind": "destination",
                    "name": name, "category": category})
    nicknames = st.account_nicknames()
    accounts = {a["account_id"]: nicknames.get(a["account_id"])
                or _base_name(a.get("account_name") or a["account_id"])
                for a in st.accounts()}
    for r in st.exclusion_rules():
        out.append({"id": f"exclusion:{r['id']}", "kind": "exclusion",
                    "name": _exclusion_name(r, accounts), "category": None,
                    "reason": r.get("reason") or "", "matched": r.get("matched", 0)})
    return out


@bp.get("/rules")
def list_rules():
    from . import kinds, marks, txlist
    st = store()
    rules = _rules(st)
    bank_names = _merchant_names(st)
    txns = st.all_transactions()
    return jsonify({"rules": rules, "count": len(rules), "kinds": kinds.category_kinds(st),
                    "pearl_kinds": kinds.pearl_decides(st, txns, date.fromisoformat(_today_iso())),
                    # Her names for merchants, and her tags (2026-10-14).
                    "names": [{"merchant": bank_names.get(key) or key.title(), "key": key,
                               "name": name}
                              for key, name in sorted(st.merchant_names().items())],
                    "tags": txlist.tag_totals(_txlist_rows(st, everything=True)),
                    "hidden": sorted(marks.hidden_categories(st))})


@bp.put("/rules/kinds")
def set_rule_kind():
    """Mark a category always Fixed or always Variable (finance/kinds.py),
    or let Pearl decide again with `kind` null."""
    from . import kinds
    body = request.get_json(silent=True) or {}
    try:
        data = kinds.set_category_kind(store(), str(body.get("category") or ""), body.get("kind"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "kinds": data})


def _split(rule_id: str) -> tuple[str, str]:
    kind, _, key = (rule_id or "").partition(":")
    return kind, key


@bp.put("/rules/<path:rule_id>")
def edit_rule(rule_id: str):
    """Change what a sorting rule files things under. Rows it sorted follow."""
    from .categorize import CATEGORIES
    from .transfers import apply_transfer_matches
    st = store()
    kind, key = _split(rule_id)
    category = (request.get_json(silent=True) or {}).get("category")
    if category not in CATEGORIES:
        return jsonify({"error": "Choose a category."}), 400
    if kind == "merchant" and key in st.overrides():
        st.set_override(key, category)
    elif kind == "destination" and key in st.destinations():
        st.set_destination(key, category, st.destination_labels().get(key, ""))
        apply_transfer_matches(st)
    else:
        return jsonify({"error": "No such rule."}), 404
    rule = next((r for r in _rules(st) if r["id"] == rule_id), None)
    return jsonify({"ok": True, "rule": rule})


@bp.delete("/rules/<path:rule_id>")
def delete_rule(rule_id: str):
    """Delete a rule (S-03). Transactions already sorted keep their category;
    a leave-out rule puts what it left out back."""
    from .transfers import RULED, apply_transfer_matches, destination
    st = store()
    kind, key = _split(rule_id)
    if kind == "merchant":
        if not st.delete_override(key):
            return jsonify({"error": "No such rule."}), 404
    elif kind == "destination":
        if key not in st.destinations():
            return jsonify({"error": "No such rule."}), 404
        keep = {}
        for t in st.all_transactions():
            if t.category_source == RULED and (destination(t) or ("",))[0] == key:
                keep[t.fingerprint] = (t.category, "user")
        st.clear_destination(key)
        if keep:
            st.write_categories(keep)
        apply_transfer_matches(st)
    elif kind == "exclusion":
        try:
            rid = int(key)
        except ValueError:
            return jsonify({"error": "No such rule."}), 404
        if not st.delete_exclusion_rule(rid):
            return jsonify({"error": "No such rule."}), 404
        _reclassify(st)
    elif kind == "name":
        if key not in st.merchant_names():
            return jsonify({"error": "No such rule."}), 404
        st.set_merchant_name(key, None)
    else:
        return jsonify({"error": "No such rule."}), 404
    return jsonify({"ok": True, "count": len(_rules(st))})
