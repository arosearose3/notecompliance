"""
Standard G1: Ongoing discharge planning.
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


class CheckG1:
    """Discharge planning: criteria, barriers, and support systems."""
    standard_id = "G1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in ("intake", "treatment_plan", "progress"):
            return not_applicable("G1")

        # For progress notes: only required on major change notes
        if note.note_type == "progress":
            discharge_ref = bool(re.search(
                r"\bdischarge\s+plan|\bcriteria\s+for\s+discharge\b",
                note.full_text, re.IGNORECASE,
            ))
            if not discharge_ref:
                return not_applicable("G1", "Progress note: no discharge planning reference found — conditional check N/A.")

        dc_plan = get_section(note.sections, "discharge_plan")
        support = get_section(note.sections, "support_systems")
        barriers = get_section(note.sections, "barriers")

        found = []
        missing = []
        for label, text in [("discharge criteria", dc_plan), ("support systems", support), ("barriers", barriers)]:
            if text:
                found.append(label)
            else:
                missing.append(label)

        if not missing:
            return passed("G1", f"Discharge planning sub-items present: {found}.")

        if not found:
            return failed("G1", "No discharge planning sub-items found (criteria, barriers, support systems).")

        answer = judge.evaluate(
            question=(
                "Does this note address all three discharge planning elements: "
                "(1) criteria for discharge, (2) barriers to completing treatment and interventions to address them, "
                "(3) identification of support systems or lack thereof?"
            ),
            context=note.full_text[:4000],
        )
        return CheckResult(
            standard_id="G1",
            verdict=answer.verdict,
            rationale=f"Found: {found}. Missing by section search: {missing}. {answer.rationale}",
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )
