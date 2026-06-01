"""
Standards K1–K2: Telehealth documentation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, manual_review, not_applicable, passed,
)
from compliance.checks.f_progress import CheckF3  # K1 is same logic as F3

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note


class CheckK1:
    """Telehealth must be noted in the treatment record if service is virtual."""
    standard_id = "K1"

    def __init__(self) -> None:
        self._f3 = CheckF3()

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        result = self._f3.run(note, judge, bundle)
        # Re-label standard_id
        return result.__class__(
            standard_id="K1",
            verdict=result.verdict,
            rationale=result.rationale,
            excerpts=result.excerpts,
            page_numbers=result.page_numbers,
            judge_used=result.judge_used,
        )


class CheckK2:
    """State-specific telehealth requirements — always manual_review."""
    standard_id = "K2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        return manual_review(
            "K2",
            "State-specific telehealth regulations vary and cannot be verified "
            "automatically. Review the telehealth requirements for the state(s) "
            "in which the clinician is licensed.",
        )
