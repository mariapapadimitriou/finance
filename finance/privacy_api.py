"""Profile › Privacy: consents, notifications, her data, and deleting the
account. Pearl Handoff, page "Accounts & settings":

* THL-115 T-04 How we protect you (settings), with her live connections.
* THL-117 CN-04 / CN-05 Privacy and consent: each consent with its date; the
  optional ones (sorting with AI, tips by email, usage data) change here and
  every change is logged with its time (`users.record_consents`).
* THL-139 N-01 / N-02 Notifications: stored only — push is the iOS app's,
  which isn't built, and none of these moments sends an email yet.
* THL-116 D-01 to D-05 Your data: the .zip (`data_export`), and deleting the
  account after a passkey, an email code or (for accounts from before Pearl)
  the password confirms it's her (`account_deletion`).
"""

from __future__ import annotations

import sys

from flask import Response, current_app, g, jsonify, request, session

from . import account_deletion, auth, data_export, mailer, passkeys, signin_codes, users
from .api import bp, store


def _user():
    return g.get("user")


def _base():
    return current_app.config["STORE"]


def _no_account():
    """Only reached where nobody signs in (a local ledger with no accounts;
    anywhere else the sign-in gate answers first): there is no account to
    save a choice to, or to delete."""
    return jsonify({"error": "There’s no account here. Make one to use this.",
                    "no_account": True}), 400


def _fresh(user):
    return users.by_id(_base(), user.id)


# ── T-04 and CN-04 ───────────────────────────────────────────────────────

def _connections(st) -> list[dict]:
    """Each linked bank, how many accounts it brings, and how it is."""
    from . import milestones
    from .profile_api import _linked_rows
    rows = _linked_rows(st)
    out = []
    for item in st.plaid_items():
        state = milestones.connection_state(item) or "healthy"
        out.append({"item_id": item["item_id"],
                    "institution": item.get("institution") or "Your bank",
                    "accounts": sum(1 for r in rows if r.get("item_id") == item["item_id"]),
                    "last_synced": item.get("last_synced"),
                    "state": state})
    return out


def _privacy(user) -> dict:
    return {"consents": users.effective_consents(user),
            "log": users.consent_log(_base(), user.id),
            "contact": mailer.reply_address(),
            "email": user.email,
            "connections": _connections(store())}


@bp.get("/privacy")
def privacy_page():
    user = _user()
    if user is None:
        return jsonify({"consents": {}, "log": [], "contact": mailer.reply_address(),
                        "email": None, "connections": _connections(store())})
    return jsonify(_privacy(_fresh(user)))


@bp.put("/privacy/consents")
def privacy_consent():
    """Give or take back one optional consent (CN-04, CN-05). The ones Pearl
    needs are withdrawn by deleting the account (D-03)."""
    user = _user()
    if user is None:
        return _no_account()
    body = request.get_json(silent=True) or {}
    key = str(body.get("key") or "")
    if key in users.REQUIRED:
        return jsonify({"error": "Pearl needs this one to work. To withdraw it, "
                                 "delete your account."}), 400
    if key not in users.OPTIONAL or not isinstance(body.get("value"), bool):
        return jsonify({"error": "Unknown consent."}), 400
    user = users.record_consents(_base(), user.id, {key: body["value"]}, source="settings")
    return jsonify(_privacy(user))


# ── N-01 / N-02 ──────────────────────────────────────────────────────────

def _notifications(user) -> dict:
    # Email is only for someone who said yes to email from Pearl (CN-03).
    tips = users.effective_consents(user).get("tips") or {}
    return {"prefs": users.notification_prefs(user), "email_ok": bool(tips.get("value"))}


@bp.get("/notifications")
def notifications_page():
    user = _user()
    if user is None:
        return jsonify({"prefs": users.NOTIFY_DEFAULTS, "email_ok": False})
    return jsonify(_notifications(_fresh(user)))


@bp.put("/notifications")
def notifications_save():
    user = _user()
    if user is None:
        return _no_account()
    user = _fresh(user)
    body = request.get_json(silent=True) or {}
    changes = {k: body[k] for k in ("types", "quiet", "lock_amounts") if k in body}
    if not _notifications(user)["email_ok"] and any(
            (chans or {}).get("email") is True
            for chans in (changes.get("types") or {}).values() if isinstance(chans, dict)):
        return jsonify({"error": "Turn on tips and news by email in Privacy and "
                                 "consent first."}), 400
    _, problem = users.set_notifications(_base(), user.id, changes)
    if problem:
        return jsonify({"error": problem}), 400
    return jsonify(_notifications(_fresh(user)))


@bp.post("/notifications/prompt")
def notifications_prompt():
    """N-01's answer: "Turn on notifications" or "Not now"."""
    user = _user()
    if user is None:
        return _no_account()
    body = request.get_json(silent=True) or {}
    _, problem = users.set_notifications(_base(), user.id, {"prompt": {
        "answer": body.get("answer"), "milestone": body.get("milestone")}})
    if problem:
        return jsonify({"error": problem}), 400
    return jsonify(_notifications(_fresh(user)))


# ── D-01 / D-02 ──────────────────────────────────────────────────────────

def _export():
    user = _user()
    return data_export.build(_base(), _fresh(user) if user else None, store())


@bp.get("/data/export")
def data_export_summary():
    """D-02's "Your download is ready: 6 accounts and 1,306 transactions."""
    _, counts = _export()
    return jsonify({**counts, "filename": "pearl-data.zip"})


@bp.get("/data/export.zip")
def data_export_file():
    data, _ = _export()
    return Response(data, mimetype="application/zip", headers={
        "Content-Disposition": 'attachment; filename="pearl-data.zip"',
        "Cache-Control": "no-store"})


@bp.post("/data/start-over")
def data_start_over():
    """Start over: clear the transactions and her organizing; the banks stay
    and the page syncs next to bring the history back (Store.start_over).
    Confirmed by typing "start over"."""
    body = request.get_json(silent=True) or {}
    if " ".join(str(body.get("confirm") or "").lower().split()) != "start over":
        return jsonify({"error": "Type “start over” to confirm."}), 400
    from datetime import date
    from . import savings
    from .api import _today_iso
    st = store()
    removed = st.start_over()
    savings.start_over(st, date.fromisoformat(_today_iso()))
    return jsonify({"ok": True, "removed": removed, "resync": True})


# ── D-03 to D-05 ─────────────────────────────────────────────────────────

@bp.get("/account/delete")
def delete_options():
    """How she can confirm it's her (D-04)."""
    user = _user()
    if user is None:
        return _no_account()
    n = passkeys.count(_base(), user.id)
    return jsonify({"passkeys": n, "email": user.email,
                    "password": user.has_password,
                    "methods": [m for m, ok in (("passkey", n > 0), ("code", bool(user.email)),
                                                ("password", user.has_password)) if ok]})


@bp.post("/account/delete/passkey-options")
def delete_passkey_options():
    user = _user()
    if user is None:
        return _no_account()
    rp_id, _ = current_app.config["RELYING_PARTY"]()
    options, challenge = passkeys.authentication_options(rp_id)
    session["pk_delete"] = challenge
    return current_app.response_class(options, mimetype="application/json")


@bp.post("/account/delete/code")
def delete_code():
    """D-04 "Use an email code instead": a code to her own address."""
    user = _user()
    if user is None:
        return _no_account()
    if not user.email:
        return jsonify({"error": "There’s no email on this account."}), 400
    out = signin_codes.start_change(_base(), user.id, user.email, purpose=signin_codes.DELETE)
    if out.get("paused"):
        return jsonify({"error": "There were too many tries, so we’ve paused this for "
                                 "15 minutes.", "paused": True, "retry_in": out["paused"]}), 429
    if out.get("code"):
        hello = f"Hi {user.first_name}," if user.first_name else "Hi,"
        subject = f"Your Pearl code: {out['code']}"
        text = (f"{hello}\n\nYour code to delete your Pearl account is:\n\n    {out['code']}\n\n"
                "It works for 10 minutes. If you didn't ask for it, ignore this email — "
                "nothing is deleted without the code.")
        if mailer.configured():
            try:
                mailer.send(user.email, subject, text)
            except Exception:                          # noqa: BLE001
                return jsonify({"error": "The email didn’t send. Try again in a minute."}), 502
        elif not current_app.config.get("HOSTED"):
            print(f"[pearl] {subject} → {user.email}", file=sys.stderr)
    return jsonify({"ok": True, "sent_to": user.email,
                    "resend_in": out.get("resend_in", signin_codes.RESEND_AFTER)})


def _confirmed(user, body) -> tuple[bool, tuple | None]:
    """(it's her, or the reply saying why not)."""
    method = body.get("method")
    if method == "passkey":
        challenge = session.pop("pk_delete", None)
        if not challenge:
            return False, (jsonify({"error": "That took too long. Try again."}), 400)
        rp_id, origins = current_app.config["RELYING_PARTY"]()
        try:
            who = passkeys.authenticate(_base(), body.get("credential") or {},
                                        challenge, rp_id, origins)
        except Exception:                              # noqa: BLE001
            who = None
        if who is None or who.id != user.id:
            return False, (jsonify({"error": "That passkey didn’t work. Use an email "
                                             "code instead."}), 400)
        return True, None
    if method == "code":
        out = signin_codes.verify_change(_base(), user.id, body.get("code", ""),
                                         purpose=signin_codes.DELETE)
        if out.get("error") == "paused":
            return False, (jsonify({"error": "There were too many tries, so we’ve paused "
                                             "this for 15 minutes.", "paused": True}), 429)
        if out.get("error") == "wrong":
            left = out["left"]
            return False, (jsonify({"error": f"That code didn’t match. {left} "
                                             f"{'try' if left == 1 else 'tries'} left.",
                                    "wrong": True}), 400)
        if out.get("error"):
            return False, (jsonify({"error": "That code has expired. Send a new one.",
                                    "expired": True}), 400)
        return True, None
    if method == "password":
        if user.has_password and auth.verify_password(str(body.get("password", "")),
                                                      user.password_hash):
            return True, None
        return False, (jsonify({"error": "That password isn’t right."}), 400)
    return False, (jsonify({"error": "Confirm it’s you first."}), 400)


@bp.post("/account/delete")
def delete_account_now():
    """Delete the signed-in account, once she has confirmed it's her."""
    user = _user()
    if user is None:
        return _no_account()
    user = _fresh(user)
    ok, reply = _confirmed(user, request.get_json(silent=True) or {})
    if not ok:
        return reply
    done = account_deletion.delete_account(_base(), user, store(),
                                           current_app.config.get("STORES"))
    session.clear()
    sent_to = None
    if user.email:
        from . import emails
        subject, text = emails.account_deleted(user.first_name)
        if mailer.configured():
            try:
                mailer.send(user.email, subject, text)
                sent_to = user.email
            except Exception:                          # noqa: BLE001
                pass
        elif not current_app.config.get("HOSTED"):
            print(f"[pearl] {subject} → {user.email}", file=sys.stderr)
    return jsonify({"ok": True, **done, "confirmation_sent_to": sent_to})
