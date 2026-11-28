"""Signals: one detection framework (AI Phase 3, THL-310).

* `model`: the `Detection` record every detector gives.
* `adapters` and `registry`: each existing detection module, wrapped, not
  rewritten, with its version.
* `ledger`: the `detections` table, her answers to each detection against
  detector@version, and the read-only `summary` for a later health page.

No AI here and no model calls: Python detects, she confirms.
"""

from .ledger import outcome, summary
from .model import (APPLIED, CONFIRMED, KINDS, NOT_THIS, OUTCOMES, PROPOSED, REJECTED, SKIP,
                    STATUSES, STOP, UNDO, UNDONE, YES, Detection, Evidence, evidence)
from .registry import DETECTORS, run, run_all, version_of

__all__ = ["APPLIED", "CONFIRMED", "DETECTORS", "Detection", "Evidence", "KINDS", "NOT_THIS",
           "OUTCOMES", "PROPOSED", "REJECTED", "SKIP", "STATUSES", "STOP", "UNDO", "UNDONE",
           "YES", "evidence", "outcome", "run", "run_all", "summary", "version_of"]
