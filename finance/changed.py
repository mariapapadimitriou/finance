"""What a request changed, and whether anything has (2026-11-19).

Two things the iPhone needs to stop refetching whole screens:

* **Reads carry an ETag** made of the ledger's version and today's date. A
  screen that already has an answer asks again with `If-None-Match`; when
  nothing changed the server says `304` after one statement, and the phone
  keeps what it shows. (API answers stay `Cache-Control: no-store`: the
  phone keeps its own copy on purpose, browsers keep none.)

* **Writes carry a `changed` envelope**: the new version, the rows the
  change touched (described exactly as the transactions list describes
  them, so the phone can swap them in place), the ids of rows that are gone,
  the Allowance as Home shows it, and how many rows the review has. One
  hook on the blueprint adds it to every transaction-shaped write, so a
  handler doesn't have to remember to.
"""

from __future__ import annotations

import json
import os
import re

from flask import Response, g, request

_OP_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OP_HEADER = "X-Op-Id"
BASE_HEADER = "X-Base-Version"

_ID = re.compile(r"\b[0-9a-f]{20}\b")
_WRITE_PATHS = ("/api/transactions", "/api/quick-sort", "/api/review", "/api/transfers",
                "/api/exclusions", "/api/merchants", "/api/rules")
_UNSAFE = ("POST", "PUT", "PATCH", "DELETE")
# Writes whose answer is a screen of its own, or that change too much to list.
_NO_ENVELOPE = ("/api/transactions/batch/category/preview", "/api/transactions/import",
                "/api/transactions/undo")
# Reads the phone keeps; their answers depend only on the ledger and the day.
_TAGGED_READS = ("/api/home", "/api/transactions", "/api/review", "/api/quick-sort",
                 "/api/calendar", "/api/income-bills", "/api/summary", "/api/owed",
                 "/api/accounts", "/api/categories", "/api/setup-again")


def concerns(path: str, method: str) -> bool:
    """Whether this module has anything to do with the request: a read the
    phone keeps, or a write it patches from. Everything else, deleting an
    account above all, is left alone: opening the store for it after the
    ledger is gone would make the ledger again."""
    if method == "GET":
        return path.startswith(_TAGGED_READS)
    return method in _UNSAFE and path.startswith(_WRITE_PATHS) \
        and not path.startswith(_NO_ENVELOPE)


# Which build of the server answered (2026-11-20): a deploy that changes
# what a row carries must make the phone's kept copies stale even though
# the ledger's version hasn't moved. Vercel's commit when it is in the
# environment; otherwise a fingerprint of the code that shapes rows, so it
# changes with the code wherever it runs and never silently stays "dev".
def _build() -> str:
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("VERCEL_DEPLOYMENT_ID")
    if sha:
        return sha[:7]
    import hashlib
    h = hashlib.sha1()
    here = os.path.dirname(__file__)
    for name in ("api.py", "txlist.py", "changed.py", "review.py", "models.py", "transfers.py"):
        try:
            with open(os.path.join(here, name), "rb") as f:
                h.update(f.read())
        except OSError:
            continue
    return h.hexdigest()[:7]


BUILD = _build()


def etag(st, today: str) -> str:
    return f'W/"{st.version()}-{today}-{BUILD}"'


def not_modified(st, today: str):
    """A 304 when the phone already has this version's answer, else None."""
    if request.method != "GET" or not request.path.startswith(_TAGGED_READS):
        return None
    tag = etag(st, today)
    if request.headers.get("If-None-Match") == tag:
        from flask import Response
        resp = Response(status=304)
        resp.headers["ETag"] = tag
        return resp
    g._etag = tag
    return None


def tag_response(st, today: str, response):
    """The ETag on a read's answer (after any one-time fixes the read did)."""
    if request.method == "GET" and response.status_code == 200 \
            and request.path.startswith(_TAGGED_READS):
        from .request_tx import bump_versions
        bump_versions()         # a read's one-time fixes count: the tag says so
        response.headers["ETag"] = etag(st, today)
    return response


def _ids_in(reply: dict, body: dict) -> set[str]:
    ids = set(_ID.findall(request.path))
    for d in (reply, body):
        for key in ("id", "txn_id", "inflow_id", "charge_id"):
            if isinstance(d.get(key), str):
                ids.add(d[key])
        for key in ("ids", "changed_ids", "linked", "unlinked"):
            if isinstance(d.get(key), list):
                ids.update(x for x in d[key] if isinstance(x, str))
        t = d.get("transaction")
        if isinstance(t, dict) and isinstance(t.get("id"), str):
            ids.add(t["id"])
        # A deposit's parts are rows of their own (finance/parts.py): new
        # ones the list must gain.
        for p in d.get("parts") or []:
            if isinstance(p, dict) and isinstance(p.get("id"), str):
                ids.add(p["id"])
    undo = reply.get("undo")
    if isinstance(undo, dict):
        for r in undo.get("rows") or []:
            if isinstance(r, dict) and isinstance(r.get("id"), str):
                ids.add(r["id"])
        for key in ("paybacks", "refunds"):
            for r in undo.get(key) or []:
                if isinstance(r, dict):
                    ids.update(v for v in r.values() if isinstance(v, str) and _ID.fullmatch(v))
    return {i for i in ids if _ID.fullmatch(i)}


def envelope(st, today: str, response, describe, allowance, review_count):
    """Add `changed` to a write's JSON answer. `describe(ids)` gives the rows
    as the list shows them, `allowance()` the Allowance, `review_count()`
    the review's count."""
    if request.method not in _UNSAFE or response.status_code != 200 \
            or not request.path.startswith(_WRITE_PATHS) \
            or request.path.startswith(_NO_ENVELOPE) or request.args.get("dry") \
            or not response.is_json:
        return response
    reply = response.get_json(silent=True)
    if not isinstance(reply, dict) or "changed" in reply:
        return response
    body = request.get_json(silent=True) if request.is_json else None
    body = body if isinstance(body, dict) else {}
    from .request_tx import bump_versions
    bump_versions()
    ids = _ids_in(reply, body)
    rows = describe(ids) if ids else {}
    reply["changed"] = {
        "version": st.version(),
        "etag": etag(st, today),
        "rows": [rows[i] for i in ids if i in rows],
        "removed": sorted(i for i in ids if i not in rows),
        "allowance": allowance(),
        "review_count": review_count(),
    }
    response.set_data(json.dumps(reply))
    return response


def claim(st):
    """Before a write the phone named (`X-Op-Id`): the earlier answer if
    this is a repeat, 409 if the first attempt is still running, else None
    and the write goes ahead and is recorded by `record`."""
    if request.method not in _UNSAFE:
        return None
    op_id = request.headers.get(OP_HEADER)
    if not op_id:
        return None
    if not _OP_ID.match(op_id):
        return Response(json.dumps({"error": "That edit's id doesn't look right."}),
                        status=400, mimetype="application/json")
    base = request.headers.get(BASE_HEADER)
    try:
        base_version = int(base) if base else None
    except ValueError:
        base_version = None
    earlier = st.claim_op(op_id, base_version)
    if earlier is None:
        g._op_id = op_id
        return None
    if earlier["status"] == 0:
        resp = Response(json.dumps({"error": "That edit is still being applied.", "retry": True}),
                        status=409, mimetype="application/json")
        resp.headers["Retry-After"] = "2"
        return resp
    resp = Response(earlier["result"] or "{}", status=earlier["status"],
                    mimetype="application/json")
    resp.headers["X-Replayed"] = "1"
    return resp


def record(st, response):
    """After a write the phone named: keep its answer for a repeat."""
    op_id = g.get("_op_id")
    if not op_id:
        return response
    if response.status_code >= 500:
        st.forget_op(op_id)
        return response
    from .request_tx import bump_versions
    bump_versions()
    body = response.get_data(as_text=True) if response.is_json else None
    st.finish_op(op_id, response.status_code, body, st.version())
    return response
