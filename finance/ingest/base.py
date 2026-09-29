"""The ingestion contract.

Everything downstream -- dedupe, categorization, analytics, insights -- consumes
`Transaction` objects and never learns where they came from. A source only has
to answer three questions: who am I, am I usable right now, and what
transactions can you give me.

Adding Plaid later means implementing this interface, not touching analytics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..models import Transaction


@dataclass
class SourceStatus:
    """Whether a source can actually run, and what to do if it can't."""

    key: str
    label: str
    available: bool
    detail: str = ""
    setup_url: str = ""
    setup_steps: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "available": self.available,
            "detail": self.detail,
            "setup_url": self.setup_url,
            "setup_steps": self.setup_steps or [],
        }


@dataclass
class IngestResult:
    """What one ingestion run produced, before dedupe against the store."""

    transactions: list[Transaction]
    account_id: str = ""
    account_name: str = ""
    format_key: str = ""
    format_label: str = ""
    confidence: float = 0.0
    skipped_rows: int = 0
    warnings: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "count": len(self.transactions),
            "account_id": self.account_id,
            "account_name": self.account_name,
            "format_key": self.format_key,
            "format_label": self.format_label,
            "confidence": round(self.confidence, 3),
            "skipped_rows": self.skipped_rows,
            "warnings": self.warnings or [],
        }


class TransactionSource(ABC):
    """Base class for every way transactions can enter the app."""

    key: str = ""
    label: str = ""

    @abstractmethod
    def status(self) -> SourceStatus:
        """Report whether this source is configured and ready to use."""

    @abstractmethod
    def fetch(self, **kwargs) -> list[IngestResult]:
        """Pull transactions. Kwargs are source-specific.

        CSV takes uploaded file payloads; Plaid takes an item/date range.
        Each result corresponds to one account's worth of rows.
        """


_REGISTRY: dict[str, TransactionSource] = {}


def register(source: TransactionSource) -> TransactionSource:
    _REGISTRY[source.key] = source
    return source


def get_source(key: str) -> TransactionSource | None:
    return _REGISTRY.get(key)


def all_sources() -> list[TransactionSource]:
    return list(_REGISTRY.values())
