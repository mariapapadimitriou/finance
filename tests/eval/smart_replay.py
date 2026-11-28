"""Smart vs Rules (THL-309 AC 14): replay the same new purchases through
both modes and measure how often Pearl's answer is right.

    python3 tests/eval/smart_replay.py        # the comparison table

For each labelled ledger (tests/eval/smart_fixtures/*.json; real cases,
Anastasia's among them once she shares them), the history and her answers go in, she says
Yes to every pattern Pearl asks about, the switch goes on, and then the new
purchases arrive. Each mode then runs its sync:

* **Rules**: pattern_sort.run, as today.
* **Smart**: smart_sort.run with a fake model (no network, deterministic):
  it knows a few words a shop's name may carry ("pharmacy", "bistro"),
  picks the allowed answer they point to, and otherwise agrees with Python
  (the pattern, or the first answer Python allows).

What Pearl answers for a new purchase is what it sorted by itself, or the
guess on its Quick sort card (a guess of Other is no guess). Precision is
right ÷ answered, per mode; Smart ships only if it is no lower than Rules.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

FIXTURES = os.path.join(HERE, "smart_fixtures")

# The fake model's only knowledge: words in a shop's name. A test fake, not
# product code: Pearl itself never names a shop or a word list.
WORDS = {"pharmacy": "Health", "bistro": "Dining", "bakery": "Coffee", "market": "Groceries",
         "cafe": "Coffee", "diner": "Dining"}


class FakeModel:
    """Stands in for Claude on the sort_reason route."""

    def __init__(self):
        self.calls = 0

    def send(self, *, model, system, messages, tools=None, max_tokens=1024, effort="low"):
        from finance.ai import client as client_mod
        self.calls += 1
        enum = tools[0]["input_schema"]["properties"]["answer"]["enum"]
        body = json.loads(messages[0]["content"])
        shop = body["shop"].lower()
        pick = next((c for w, c in WORDS.items() if w in shop and c in enum), None)
        if pick is None:
            pick = body.get("pattern") or enum[0]
        reason = f"Looks like {body['shop']}."
        return client_mod.Reply(model=model, stop_reason="tool_use", input_tokens=80, output_tokens=10,
                                tool_calls=[{"id": "t", "name": "pick",
                                             "input": {"answer": pick, "reason": reason}}])


@dataclass
class Score:
    mode: str
    answered: int = 0
    right: int = 0
    auto: int = 0
    auto_right: int = 0
    rows: list = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        return round(self.right / self.answered, 4) if self.answered else None

    @property
    def auto_precision(self) -> float | None:
        return round(self.auto_right / self.auto, 4) if self.auto else None


def _ledger(directory: str, fx: dict, tag: str):
    """(store, base, {fingerprint: truth}) with the history in, her Yes to
    every pattern, the switch on, then the new purchases."""
    from finance import pattern_sort as ps
    from finance import users
    from finance.ingest.base import IngestResult
    from finance.ingest.plaid_source import map_plaid_transaction
    from finance.pipeline import ingest
    from finance.store import Store

    st = Store(os.path.join(directory, f"{fx['name']}-{tag}.db"), url="")
    base = Store(os.path.join(directory, f"{fx['name']}-{tag}-base.db"), url="")
    users.ensure_table(base)
    accounts = {k: {"account_id": k, **v} for k, v in fx["accounts"].items()}

    def put(items):
        rows = [map_plaid_transaction({"transaction_id": i["ref"], **{k: v for k, v in i.items() if k != "new"}},
                                      accounts) for i in items]
        ingest(st, IngestResult(transactions=rows), filename=f"{fx['name']}.json")

    put([i for i in fx["transactions"] if not i.get("new")])
    by_ref = {(t.raw or {}).get("plaid_id"): t.fingerprint for t in st.all_transactions()}
    for a in fx.get("answers") or []:
        st.set_transaction_category(by_ref[a["ref"]], a["category"])
    ps.switched_on(st)
    for ask in ps.pending(st, fx["today"]):
        ps.confirm(st, ask["id"], fx["today"])
    put([i for i in fx["transactions"] if i.get("new")])
    by_ref = {(t.raw or {}).get("plaid_id"): t.fingerprint for t in st.all_transactions()}
    truth = {by_ref[c["ref"]]: c["truth"] for c in fx["cases"]}
    return st, base, truth


def _answers(st, today: str, truth: dict, sorted_recs: list) -> dict:
    """{fingerprint: (answer, how)} for the labelled new purchases."""
    from finance.review import _for_store
    out = {r["txn"]: (r["answer"], "auto") for r in sorted_recs if r["txn"] in truth}
    review = _for_store(st, today)
    for it in review.get("unsure_category") or []:
        tid = it["txn"]["id"]
        if tid in truth and tid not in out and it.get("guess") and it["guess"] != "Other":
            out[tid] = (it["guess"], "guess")
    return out


def replay_one(fx: dict, directory: str) -> dict[str, Score]:
    from finance import pattern_sort as ps
    from finance import smart_sort
    scores = {}
    for mode in ("rules", "smart"):
        st, base, truth = _ledger(directory, fx, mode)
        if mode == "rules":
            recs = ps.run(st, fx["today"])
        else:
            smart_sort.set_mode(base, st, None, smart_sort.SMART, consent=True)
            recs = smart_sort.run(st, fx["today"], base=base, user_id=1, client=FakeModel())["sorted"]
        s = Score(mode)
        for tid, (answer, how) in _answers(st, fx["today"], truth, recs).items():
            ok = answer == truth[tid]
            s.answered += 1
            s.right += ok
            if how == "auto":
                s.auto += 1
                s.auto_right += ok
            s.rows.append((fx["name"], st.get_transaction(tid).merchant, how, answer, truth[tid]))
        scores[mode] = s
    return scores


def load_fixtures() -> list[dict]:
    out = []
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def replay(directory: str | None = None) -> dict[str, Score]:
    total = {"rules": Score("rules"), "smart": Score("smart")}
    with tempfile.TemporaryDirectory() as tmp:
        where = directory or tmp
        for fx in load_fixtures():
            for mode, s in replay_one(fx, where).items():
                t = total[mode]
                t.answered += s.answered
                t.right += s.right
                t.auto += s.auto
                t.auto_right += s.auto_right
                t.rows += s.rows
    return total


def table(scores: dict[str, Score]) -> str:
    lines = [f"{'mode':<6} {'answered':>8} {'right':>5} {'precision':>9} {'auto':>5} {'auto right':>10}",
             "-" * 50]
    for mode in ("rules", "smart"):
        s = scores[mode]
        p = "n/a" if s.precision is None else f"{s.precision:.2f}"
        lines.append(f"{mode:<6} {s.answered:>8} {s.right:>5} {p:>9} {s.auto:>5} {s.auto_right:>10}")
    lines.append("")
    for mode in ("rules", "smart"):
        for fx, shop, how, answer, truth in scores[mode].rows:
            lines.append(f"  {mode:<6} {shop:<28} {how:<5} {answer:<12} {'ok' if answer == truth else 'want ' + truth}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table(replay()))
