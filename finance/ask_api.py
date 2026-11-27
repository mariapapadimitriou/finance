"""POST /api/ask (THL-308, AI Phase 2): Ask Pearl's answer, streamed.

Only for someone who turned Ask Pearl on (PC-24's Turn on Ask Pearl, or the
switch in Profile › Privacy, CN-06): the consent is `ai_ask`, kept with its
time and logged like every other (`users.record_consents`), and withdrawn
the same way. Anyone else gets 403 and nothing is sent anywhere.

    POST /api/ask  {text, plans?}  →  application/x-ndjson (finance/ask.py)

It only reads: the cards an answer can hold change things through the
endpoints they already use, and only on her tap (finance/chat.py).
"""

from __future__ import annotations

import json
import time
from datetime import date

from flask import Response, current_app, g, jsonify, request, stream_with_context

from . import api as core
from . import ask, users
from .api import bp, store

CONSENT = "ai_ask"


LOCAL_KEY = "ai_ask_consent"


def local_consent(st) -> dict | None:
    """A local ledger with no accounts: {"value", "at"} or None."""
    try:
        got = json.loads(st.setting(LOCAL_KEY) or "null")
    except (TypeError, ValueError):
        return None
    return got if isinstance(got, dict) and "value" in got else None


def set_local_consent(st, value: bool) -> None:
    st.set_setting(LOCAL_KEY, json.dumps({"value": bool(value), "at": time.time()}))


def on_for(user) -> bool:
    """Has this account turned Ask Pearl on (and not off since)?"""
    if user is None:
        if current_app.config.get("HOSTED"):
            return False
        return bool((local_consent(store()) or {}).get("value"))
    fresh = users.by_id(current_app.config["STORE"], user.id)
    return bool(fresh and (users.effective_consents(fresh).get(CONSENT) or {}).get("value"))


def state_for(user) -> str:
    """"on", "off" (she said no, or turned it off), or "unasked" (PC-24 shows)."""
    if user is None:
        given = None if current_app.config.get("HOSTED") else local_consent(store())
    else:
        fresh = users.by_id(current_app.config["STORE"], user.id)
        given = (fresh.consents or {}).get(CONSENT) if fresh else None
    if not isinstance(given, dict):
        return "unasked"
    return "on" if given.get("value") else "off"


@bp.post("/ask")
def ask_pearl():
    user = g.get("user")
    if not on_for(user):
        return jsonify({"error": "Turn on Ask Pearl to ask.", "ask_off": True}), 403
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    text = " ".join(str(body.get("text") or "").split())[:ask.MAX_TEXT]
    if not text:
        return jsonify({"error": "Ask Pearl something."}), 400
    st = store()
    today = date.fromisoformat(core._today_iso())
    base = current_app.config["STORE"]
    events = ask.answer(st, base=base, user_id=user.id if user else None, text=text, today=today,
                        plans=body.get("plans") is True)

    def lines():
        try:
            for ev in events:
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception:                                  # noqa: BLE001
            # Never a stack trace on her phone: Pearl's own line instead.
            current_app.logger.exception("ask failed")
            yield json.dumps({"type": "couldnt"}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"

    return Response(stream_with_context(lines()), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
