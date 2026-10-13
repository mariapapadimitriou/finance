"""Learn: the five "Before you invest" modules and her progress through them
(Pearl THL-134 GR-11 to GR-14).

The words live with the screens (`src/panels/learnModules.js`); this holds
what the server has to know to keep her place: each module's id, how many
screens it has, and its quick check's answers. Every module is four screens,
the last a quick check with no score (GR-13): any answer reveals the
explanation, and finishing needs an answer.

Progress is saved per screen, on her account, so it follows her to every
device. Finished modules count toward "Read the basics" on the readiness
checklist (THL-135 GR-16): "2 of 5 modules", ticked at five.

Stored as one JSON setting, `learn_progress`:
    {module id: {"screen": furthest screen reached (1-4),
                 "answer": her quick-check answer or null,
                 "done_on": "2026-10-13" once finished}}
"""

from __future__ import annotations

import json

KEY = "learn_progress"

MODULES = [
    {"id": "tfsa-rrsp-fhsa", "screens": 4, "options": ["tfsa", "rrsp", "fhsa"], "answer": "fhsa"},
    {"id": "index-funds-etfs", "screens": 4, "options": ["true", "false"], "answer": "false"},
    {"id": "risk-time-horizon", "screens": 4, "options": ["steady", "invested"], "answer": "steady"},
    {"id": "fees", "screens": 4, "options": ["one_time", "yearly"], "answer": "yearly"},
    {"id": "robo-or-self-directed", "screens": 4, "options": ["robo", "self"], "answer": "robo"},
]
BY_ID = {m["id"]: m for m in MODULES}


def load(st) -> dict:
    """Her progress, keyed by module id; anything unrecognised is dropped."""
    try:
        raw = json.loads(st.setting(KEY) or "{}")
    except (TypeError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for mid, row in raw.items():
        if mid in BY_ID and isinstance(row, dict):
            out[mid] = {"screen": int(row.get("screen") or 0), "answer": row.get("answer"),
                        "done_on": row.get("done_on")}
    return out


def payload(st) -> dict:
    """GR-11: each module's state, how many are read, and the next to open."""
    progress = load(st)
    modules = []
    for m in MODULES:
        row = progress.get(m["id"], {})
        answer = row.get("answer")
        modules.append({
            "id": m["id"], "screens": m["screens"],
            "screen": min(row.get("screen") or 0, m["screens"]),
            "done": bool(row.get("done_on")), "done_on": row.get("done_on"),
            "answer": answer, "correct": answer == m["answer"] if answer else None,
        })
    read = sum(1 for m in modules if m["done"])
    nxt = next((m["id"] for m in modules if not m["done"]), None)
    return {"modules": modules, "read": read, "of": len(modules), "next": nxt}


def update(st, module_id: str, body: dict, today: str) -> tuple[dict | None, str | None]:
    """Save her place, her quick-check answer, or that she finished.
    Returns (payload, None) or (None, an error to show)."""
    m = BY_ID.get(module_id)
    if not m:
        return None, "There’s no module by that name."
    progress = load(st)
    row = progress.get(module_id, {"screen": 0, "answer": None, "done_on": None})
    if "screen" in body:
        try:
            screen = int(body["screen"])
        except (TypeError, ValueError):
            return None, "Say which screen."
        if not 1 <= screen <= m["screens"]:
            return None, "Say which screen."
        row["screen"] = max(row["screen"], screen)
    if "answer" in body:
        if body["answer"] not in m["options"]:
            return None, "Choose one of the answers."
        row["answer"] = body["answer"]
        row["screen"] = m["screens"]
    if body.get("done"):
        if not row.get("answer"):
            return None, "Choose an answer first."
        row["done_on"] = row.get("done_on") or today
        row["screen"] = m["screens"]
    progress[module_id] = row
    st.set_setting(KEY, json.dumps(progress, sort_keys=True))
    return payload(st), None


def basics(st) -> dict:
    """GR-16's "Read the basics": done once every module is finished."""
    p = payload(st)
    return {"key": "basics", "done": p["read"] == p["of"], "available": True,
            "read": p["read"], "of": p["of"], "next": p["next"]}
