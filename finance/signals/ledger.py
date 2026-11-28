"""The `detections` table and her answers to them (THL-310).

Two tables in each account's own ledger (finance/store.py's SCHEMA, made
with the rest of it), not in the shared database beside `app_ai_usage`:

* `detections`: one row per thing a detector noticed, by id
  (`detector:key`), with its rows, evidence, score, detector@version and
  status (proposed, confirmed, rejected, undone). A row Pearl sorted by
  itself under a pattern she said Yes to is a detection too, with the
  pattern as its `parent`; these replace the `pattern_sort_log` setting for
  new records (`load_sort_log` still reads that key, so nothing is lost).
* `detection_outcomes`: every Yes, Skip, Not this, Undo and Stop, and every
  row sorted by itself (`applied`), against detector@version, never
  rewritten. What precision and the Undo rate are worked out from.

Why per ledger: every row names her transactions (and a pattern names a
merchant of hers), so they belong with the rows. Deleting the account drops
them with the ledger; Start over clears them with the rest of her answers,
because the resync brings the same rows back with the same ids and kept
answers would reattach (the reason `pattern_sort_log` was cleared). The
usage table is the opposite case: one bill across accounts, no words, and it
must outlive any one ledger.

Versions: a pattern-sort row is part of what the app shows ("Pearl
sorted"), so writing one is a change to the ledger like the setting it
replaces. Status changes and outcomes are bookkeeping, written quietly in the
same transaction as the answer they record: they don't move the version, and
a request that fails takes them with it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .model import (APPLIED, CONFIRMED, NOT_THIS, OUTCOMES, PROPOSED, REJECTED, STOP, UNDO,
                    UNDONE, YES, Detection, Evidence, evidence)
from .registry import version_of

LEGACY_LOG_KEY = "pattern_sort_log"      # pattern_sort.LOG_KEY: read, not added to
# Set once a record has gone into the table: until then Needs a look, Home
# and every write's answer don't spend a statement on an empty table
# (settings are read once a request; tests/test_request_budget.py).
IN_TABLE_KEY = "pattern_sort_in_table"

# What an answer leaves a detection as, unless the caller says.
_AFTER = {YES: CONFIRMED, NOT_THIS: REJECTED, UNDO: UNDONE, STOP: UNDONE, APPLIED: CONFIRMED}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r) -> dict:
    d = dict(r)
    d["txn_ids"] = json.loads(d.get("txn_ids") or "[]")
    d["evidence"] = json.loads(d.get("evidence") or "{}")
    return d


# ── Detections ────────────────────────────────────────────────────────────

def _upsert(c, *, id: str, kind: str, detector: str, version: str, key: str, txn_ids,
            ev: dict, score, status: str, parent=None, day=None, payload=None, quiet=True) -> None:
    now = _now()
    sql = ("INSERT INTO detections (id, kind, detector, version, key, parent, txn_ids, evidence, "
           "score, status, day, payload, created_at, updated_at) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
           "ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, version = excluded.version, "
           "txn_ids = excluded.txn_ids, evidence = excluded.evidence, score = excluded.score, "
           "status = excluded.status, parent = excluded.parent, day = excluded.day, "
           "payload = excluded.payload, updated_at = excluded.updated_at")
    args = (id, kind, detector, version, key, parent, json.dumps(list(txn_ids)),
            json.dumps(ev, sort_keys=True), score, status, day, payload, now, now)
    (c.execute_quietly if quiet else c.execute)(sql, args)


def save(st, d: Detection, *, status: str | None = None) -> None:
    """Keep a detection as it was found (its status as given, or as kept)."""
    with st.conn() as c:
        kept = c.execute("SELECT status FROM detections WHERE id = ?", (d.id,)).fetchone()
        _upsert(c, id=d.id, kind=d.kind, detector=d.detector, version=d.version, key=d.key,
                txn_ids=d.txn_ids, ev=d.evidence.to_dict(), score=d.score,
                status=status or (kept["status"] if kept else d.status))


def set_status(st, detection_id: str, status: str) -> bool:
    """Put a kept detection back as it was (Undo for a Stop): no answer is
    recorded. False when Pearl hadn't kept it."""
    with st.conn() as c:
        cur = c.execute_quietly("UPDATE detections SET status = ?, updated_at = ? WHERE id = ?",
                                (status, _now(), detection_id))
    return bool(cur.rowcount and cur.rowcount > 0)


def get(st, detection_id: str) -> dict | None:
    with st.conn() as c:
        r = c.execute("SELECT * FROM detections WHERE id = ?", (detection_id,)).fetchone()
    return _row(r) if r else None


def rows(st, detector: str | None = None) -> list[dict]:
    with st.conn() as c:
        if detector is None:
            got = c.execute("SELECT * FROM detections ORDER BY seq").fetchall()
        else:
            got = c.execute("SELECT * FROM detections WHERE detector = ? ORDER BY seq",
                            (detector,)).fetchall()
    return [_row(r) for r in got]


# ── Her answers ───────────────────────────────────────────────────────────

def outcome(st, detector: str, key: str, kind: str, what: str, *, today: str | None = None,
            how: str | None = None, status: str | None = None, txn_ids=(),
            ev: Evidence | None = None, parent: str | None = None, version: str | None = None) -> str:
    """Record one answer against detector@version, and what it leaves the
    detection as: Yes confirms, Not this rejects, Undo and Stop undo, Skip
    keeps it as it was (pass `status=REJECTED` for a Skip that means
    never). The detection is made if Pearl hadn't kept it. Returns its id."""
    if what not in OUTCOMES:
        raise ValueError(f"unknown outcome {what!r}")
    did = f"{detector}:{key}"
    at = _now()
    day = today or at[:10]
    with st.conn() as c:
        kept = c.execute("SELECT * FROM detections WHERE id = ?", (did,)).fetchone()
        # Against the version that found it, when Pearl kept it.
        version = version or (kept["version"] if kept else version_of(detector))
        new_status = status or _AFTER.get(what) or (kept["status"] if kept else PROPOSED)
        if kept is None:
            _upsert(c, id=did, kind=kind, detector=detector, version=version, key=key,
                    txn_ids=txn_ids, ev=(ev or evidence()).to_dict(), score=None,
                    status=new_status, parent=parent, day=day)
        else:
            c.execute_quietly("UPDATE detections SET status = ?, updated_at = ? WHERE id = ?",
                              (new_status, at, did))
        c.execute_quietly(
            "INSERT INTO detection_outcomes (at, day, detection, kind, detector, version, outcome, how) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (at, day, did, kind, detector, version, what, how))
    return did


def outcomes(st, detector: str | None = None) -> list[dict]:
    with st.conn() as c:
        if detector is None:
            got = c.execute("SELECT * FROM detection_outcomes ORDER BY seq").fetchall()
        else:
            got = c.execute("SELECT * FROM detection_outcomes WHERE detector = ? ORDER BY seq",
                            (detector,)).fetchall()
    return [dict(r) for r in got]


# ── Pattern sort's records (replacing `pattern_sort_log`) ────────────────

def _sort_detector(rec: dict) -> str:
    return f"pattern_sort.{rec.get('kind') or 'category'}"


def _sort_kind(rec: dict) -> str:
    return "joint_theirs" if rec.get("kind") == "joint" else "category_pattern"


def _legacy(st) -> list[dict]:
    raw = st.setting(LEGACY_LOG_KEY)
    if raw in (None, ""):
        return []
    try:
        out = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def _table_log(st) -> list[dict]:
    with st.conn() as c:
        got = c.execute("SELECT payload FROM detections WHERE payload IS NOT NULL "
                        "AND detector LIKE 'pattern_sort.%' ORDER BY seq").fetchall()
    return [json.loads(r["payload"]) for r in got]


def load_sort_log(st) -> list[dict]:
    """Every record pattern_sort keeps, oldest first: those written before
    the table (the `pattern_sort_log` setting) and the table's since.
    Fresh dicts: callers change them and hand them back to `save_sort_log`."""
    from ..memo import remember
    where = (st.path, st.url, st.schema)
    return remember(("signals.sort_log",) + where,
                    lambda: _legacy(st) + (_table_log(st) if st.setting(IN_TABLE_KEY) else []))


def save_sort_log(st, log: list[dict], today: str | None = None) -> None:
    """Write back what changed: a record from the old setting goes back
    there (so its Undo still works), any other into the table. A record
    seen for the first time, not undone, is a row Pearl sorted (`applied`)."""
    legacy = _legacy(st)
    old_ids = {r.get("id") for r in legacy}
    mine = [r for r in log if r.get("id") in old_ids]
    if mine != legacy and (mine or legacy):
        st.set_setting(LEGACY_LOG_KEY, json.dumps(mine, sort_keys=True))
    fresh = [r for r in log if r.get("id") not in old_ids]
    if not fresh:
        return
    with st.conn() as c:
        got = c.execute("SELECT id, payload FROM detections WHERE payload IS NOT NULL "
                        "AND detector LIKE 'pattern_sort.%'").fetchall()
    stored = {r["id"]: r["payload"] for r in got}
    if not st.setting(IN_TABLE_KEY):
        st.set_setting(IN_TABLE_KEY, "1")
    with st.conn() as c:
        for rec in fresh:
            detector = _sort_detector(rec)
            key = f"row:{rec['id']}"
            did = f"{detector}:{key}"
            payload = json.dumps(rec, sort_keys=True)
            if stored.get(did) == payload:
                continue
            status = UNDONE if rec.get("undone") else CONFIRMED
            _upsert(c, id=did, kind=_sort_kind(rec), detector=detector,
                    version=version_of(detector), key=key, txn_ids=[rec["txn"]],
                    ev=evidence(count=rec.get("count"), options=(rec.get("answer") or "",)).to_dict(),
                    score=None, status=status, parent=f"{detector}:{rec['pattern']}",
                    day=rec.get("day"), payload=payload, quiet=False)
            if did not in stored and not rec.get("undone"):
                c.execute_quietly(
                    "INSERT INTO detection_outcomes (at, day, detection, kind, detector, version, "
                    "outcome, how) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (rec.get("at") or _now(), rec.get("day") or today or _now()[:10], did,
                     _sort_kind(rec), detector, version_of(detector), APPLIED, "pattern"))


# ── For a health page (read only) ─────────────────────────────────────────

def summary(st) -> dict:
    """Per detector@version: how many it found that she answered, and how
    they went. precision = Yes ÷ (Yes + Not this), with Skips apart (a Skip
    is "not now", not "wrong"); undo_rate = (Undo + Stop) ÷ (Yes + rows it
    sorted by itself). None where there's nothing to divide by. Reads only."""
    with st.conn() as c:
        got = c.execute("SELECT detector, version, outcome, COUNT(*) AS n FROM detection_outcomes "
                        "GROUP BY detector, version, outcome").fetchall()
        found = c.execute("SELECT detector, version, COUNT(*) AS n FROM detections "
                          "WHERE parent IS NULL GROUP BY detector, version").fetchall()
    per: dict[tuple[str, str], dict] = {}

    def slot(det, ver):
        return per.setdefault((det, ver), {"detector": det, "version": ver, "detections": 0,
                                           **{o: 0 for o in OUTCOMES}})
    for r in got:
        slot(r["detector"], r["version"])[r["outcome"]] = int(r["n"])
    for r in found:
        slot(r["detector"], r["version"])["detections"] = int(r["n"])
    out = []
    for (_, _), s in sorted(per.items()):
        judged = s[YES] + s[NOT_THIS]
        acted = s[YES] + s[APPLIED]
        s["answered"] = sum(s[o] for o in OUTCOMES if o != APPLIED)
        s["precision"] = round(s[YES] / judged, 4) if judged else None
        s["undo_rate"] = round((s[UNDO] + s[STOP]) / acted, 4) if acted else None
        out.append(s)
    return {"detectors": out,
            "answered": sum(s["answered"] for s in out),
            "applied": sum(s[APPLIED] for s in out)}
