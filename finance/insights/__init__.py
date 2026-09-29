"""Insight generation: recurring-charge detection and the savings rule engine."""

from .recurring import detect_recurring, recurring_summary  # noqa: F401
from .rules import Finding, findings_summary, generate_findings  # noqa: F401
