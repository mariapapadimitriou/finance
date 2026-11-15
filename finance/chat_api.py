"""Pearl chat's endpoints (PC-01 to PC-13; finance/chat.py). Every one only
reads: the chat's cards change things through the endpoints they already use
(see finance/chat.py), and only when she taps Yes, Set it or Make it.

* GET  /api/chat                   PB-01's "has a suggestion", her categories and people
* POST /api/chat/tell              {text, category?, days?, people?, ids?}: one proposal per transaction
* POST /api/chat/spending          {text?, category?, month?, merchant?}: PC-04's answer
* GET  /api/chat/subscriptions     Find subscriptions
* GET  /api/chat/asks              the trip and pattern cards Quick sort has too (PC-08, PC-09)
* POST /api/chat/plan              {text?, category?}: PC-12's proposal

POST is only for carrying what she said; none of them saves it.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import chat
from .api import bp, store

MAX_TEXT = 500


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _text(body: dict) -> str:
    return " ".join(str(body.get("text") or "").split())[:MAX_TEXT]


def _str(body: dict, key: str) -> str | None:
    v = body.get(key)
    return str(v).strip()[:80] if isinstance(v, str) and v.strip() else None


def _list(body: dict, key: str) -> list[str] | None:
    v = body.get(key)
    if not isinstance(v, list):
        return None
    return [str(x)[:80] for x in v if isinstance(x, (str, int, float))][:31]


@bp.get("/chat")
def chat_start():
    st = store()
    return jsonify(chat.start(st, st.all_transactions(), _today()))


@bp.post("/chat/tell")
def chat_tell():
    body = _body()
    text = _text(body)
    if not text:
        return jsonify({"error": "Tell Pearl what you did."}), 400
    st = store()
    return jsonify(chat.tell(st, st.all_transactions(), _today(), text, category=_str(body, "category"),
                             days=_list(body, "days"), people=_list(body, "people"),
                             ids=_list(body, "ids")))


@bp.post("/chat/spending")
def chat_spending():
    body = _body()
    st = store()
    return jsonify(chat.spending(st, st.all_transactions(), _today(), text=_text(body),
                                 category=_str(body, "category"), month=_str(body, "month"),
                                 merchant=_str(body, "merchant")))


@bp.get("/chat/subscriptions")
def chat_subscriptions():
    st = store()
    return jsonify(chat.subscriptions(st, st.all_transactions(), _today()))


@bp.get("/chat/asks")
def chat_asks():
    st = store()
    return jsonify(chat.asks(st, st.all_transactions(), _today()))


@bp.post("/chat/plan")
def chat_plan():
    body = _body()
    st = store()
    return jsonify(chat.plan(st, st.all_transactions(), _today(), text=_text(body),
                             category=_str(body, "category")))
