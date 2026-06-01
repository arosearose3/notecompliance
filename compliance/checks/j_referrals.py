"""
Standard J1: Referrals to clinicians, services, community resources.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, failed, manual_review, not_applicable, passed,
)
from compliance.extract.sections import get_section

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note

RE_REFERRAL_KEYWORD = re.compile(
    r"\breferred?\s+(?:to|for)\b|\breferral\b|\brecommended\s+(?:to|for|a|an)\b"
    r"|\bscheduled\s+with\b|\bconnected\s+(?:to|with)\b"
    r"|\bcommunity\s+resource\b|\bwellness\s+program\b",
    re.IGNORECASE,
)

RE_UNMET_NEED = re.compile(
    r"\bneed(?:s)?\s+(?:additional|further|more|continued)\b"
    r"|\bgap\s+in\s+(?:care|services)\b"
    r"|\bunable\s+to\s+(?:provide|address)\b"
    r"|\boutside\s+(?:scope|referral\s+needed)\b",
    re.IGNORECASE,
)


class CheckJ1:
    """Referrals to clinicians, services, community resources, wellness programs."""
    standard_id = "J1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        # Conditional: only applies when unmet needs are identified
        has_unmet_need = bool(RE_UNMET_NEED.search(note.full_text))
        referral_section = get_section(note.sections, "referrals")
        has_referral = bool(referral_section) or bool(RE_REFERRAL_KEYWORD.search(note.full_text))

        if not has_unmet_need and not has_referral:
            return not_applicable("J1", "No unmet needs or referral language found — conditional check N/A.")

        if has_referral:
            return passed("J1", "Referral(s) documented.", excerpts=[referral_section[:200]] if referral_section else [])

        # Unmet need identified but no referral
        answer = judge.evaluate(
            question=(
                "Does this note document referrals to clinicians, services, "
                "community resources, or wellness programs for any unmet needs identified?"
            ),
            context=note.full_text[:4000],
        )
        return CheckResult(
            standard_id="J1",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )
