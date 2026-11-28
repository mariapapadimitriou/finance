"""The one record every detector gives (AI Phase 3, THL-310).

A `Detection` is something Pearl noticed in her ledger: what kind of thing
(`kind`), which rows (`txn_ids`), the facts behind it (`evidence`), how sure
the detector is (`score`), which detector and version found it, and where it
stands (`status`). Python decides; she confirms: nothing here sorts or
saves anything, and a detection is only ever `proposed` until her Yes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# What was noticed. The nine of THL-310, plus two the existing modules find
# that none of the nine fit: a payback (pairs.py: money in that pays back one
# purchase) and the person on an e-Transfer (etransfers.py).
KINDS = ("income", "bill", "subscription", "trip", "transfer_pair", "card_payment",
         "joint_theirs", "category_pattern", "duplicate", "payback", "party")

PROPOSED, CONFIRMED, REJECTED, UNDONE = "proposed", "confirmed", "rejected", "undone"
STATUSES = (PROPOSED, CONFIRMED, REJECTED, UNDONE)

# What she did with one, each recorded against detector@version:
# Yes, Skip, Not this, Undo and Stop; and `applied`, a row Pearl sorted by
# itself under a pattern she had said Yes to (pattern_sort.run).
YES, SKIP, NOT_THIS, UNDO, STOP, APPLIED = "yes", "skip", "not_this", "undo", "stop", "applied"
OUTCOMES = (YES, SKIP, NOT_THIS, UNDO, STOP, APPLIED)

Scalar = str | int | float | bool | None


@dataclass(frozen=True)
class Evidence:
    """The facts behind a detection, typed, the same shape for every
    detector: how many, when, how much, how often, and the series itself.
    `facts` holds what only one detector knows (a payer, a place), as
    plain values; `options` the answers it offers, likeliest first."""

    count: int | None = None
    first: str | None = None              # ISO day
    last: str | None = None
    dates: tuple[str, ...] = ()
    amount: float | None = None           # the usual amount
    amounts: tuple[float, ...] = ()
    cadence: str | None = None            # weekly, biweekly, monthly, …
    series: tuple[tuple[str, float], ...] = ()     # (day, amount), oldest first
    options: tuple[str, ...] = ()
    facts: tuple[tuple[str, Scalar], ...] = ()     # sorted (name, value) pairs

    def fact(self, name: str, default: Scalar = None) -> Scalar:
        return dict(self.facts).get(name, default)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dates"] = list(self.dates)
        d["amounts"] = list(self.amounts)
        d["series"] = [list(p) for p in self.series]
        d["options"] = list(self.options)
        d["facts"] = dict(self.facts)
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "Evidence":
        d = d or {}
        return cls(count=d.get("count"), first=d.get("first"), last=d.get("last"),
                   dates=tuple(d.get("dates") or ()), amount=d.get("amount"),
                   amounts=tuple(d.get("amounts") or ()), cadence=d.get("cadence"),
                   series=tuple(tuple(p) for p in d.get("series") or ()),
                   options=tuple(d.get("options") or ()),
                   facts=tuple(sorted((d.get("facts") or {}).items())))


def evidence(*, count=None, first=None, last=None, dates=(), amount=None, amounts=(),
             cadence=None, series=(), options=(), **facts) -> Evidence:
    """Evidence from plain values: lists become tuples, amounts rounded to
    the cent, and anything else given by name becomes a fact."""
    def money(x):
        return None if x is None else round(float(x), 2)
    return Evidence(count=None if count is None else int(count), first=first, last=last,
                    dates=tuple(dates), amount=money(amount),
                    amounts=tuple(money(a) for a in amounts), cadence=cadence,
                    series=tuple((str(d), money(a)) for d, a in series),
                    options=tuple(options),
                    facts=tuple(sorted((k, v) for k, v in facts.items() if v is not None)))


@dataclass(frozen=True)
class Detection:
    kind: str
    txn_ids: tuple[str, ...]
    evidence: Evidence
    detector: str
    version: str
    key: str                              # what it is about, stable from run to run
    score: float | None = None
    status: str = PROPOSED

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind!r}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}")

    @property
    def id(self) -> str:
        return f"{self.detector}:{self.key}"

    @property
    def tag(self) -> str:
        """detector@version, what every outcome is recorded against."""
        return f"{self.detector}@{self.version}"

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "txn_ids": list(self.txn_ids),
                "evidence": self.evidence.to_dict(), "score": self.score,
                "detector": self.detector, "version": self.version, "key": self.key,
                "status": self.status}
