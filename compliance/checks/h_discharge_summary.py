"""
Standards H1–H3: Discharge summary elements.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, failed, manual_review, not_applicable, passed,
)
from compliance.extract.sections import get_section, has_section

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note


class CheckH1:
    """Reason for treatment episode."""
    standard_id = "H1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "discharge":
            return not_applicable("H1")

        section = get_section(note.sections, "reason_for_episode")
        if section:
            return passed("H1", "Reason for treatment episode documented.", excerpts=[section[:200]])

        return failed("H1", "No 'Reason for Treatment / Episode Summary' section found.")


class CheckH2:
    """Goals achieved or reasons not achieved."""
    standard_id = "H2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "discharge":
            return not_applicable("H2")

        section = get_section(note.sections, "goals_achieved")
        if not section:
            return failed("H2", "No goals-achieved/outcome summary section found.")

        answer = judge.evaluate(
            question=(
                "Does this discharge summary address each treatment goal — "
                "either confirming it was achieved or explaining why it was not?"
            ),
            context=section[:3000],
        )
        return CheckResult(
            standard_id="H2",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckH3:
    """Specific aftercare plan."""
    standard_id = "H3"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "discharge":
            return not_applicable("H3")

        aftercare = get_section(note.sections, "aftercare")
        if not aftercare:
            return failed("H3", "No aftercare plan section found.")

        # Rule: reject generic "follow up as needed"
        generic = bool(re.search(
            r"\bfollow[\s\-]up\s+as\s+needed\b|\bprn\b|\bif\s+needed\b",
            aftercare, re.IGNORECASE,
        ))
        if generic:
            answer = judge.evaluate(
                question=(
                    "Does the aftercare plan include specific follow-up activities "
                    "(referrals, appointments, named resources, self-care steps) "
                    "rather than only generic 'follow up as needed' language?"
                ),
                context=aftercare,
            )
            return CheckResult(
                standard_id="H3",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )

        return passed("H3", "Aftercare plan present with specific content.", excerpts=[aftercare[:200]])
