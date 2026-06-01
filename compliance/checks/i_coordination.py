"""
Standards I1–I2: Coordination of care.
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

RE_REFUSAL = re.compile(
    r"\brefused?\b|\bdeclined?\b|\bdid\s+not\s+consent\b|\bdenied?\s+(?:consent|release)\b",
    re.IGNORECASE,
)

RE_REFUSAL_REASON = re.compile(
    r"\brefused?\b[^.]*\bbecause\b|\brefused?\b[^.]*\bdue\s+to\b|\brefused?\b[^.]*\bstated?\b",
    re.IGNORECASE,
)


class CheckI1:
    """Coordination of care documented (or member refusal + reason)."""
    standard_id = "I1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        required_types = frozenset(["intake", "consultation", "discharge"])
        if note.note_type not in (*required_types, "progress"):
            return not_applicable("I1")

        coord_text = get_section(note.sections, "coordination")
        has_coord = bool(coord_text)

        if not has_coord:
            # Keyword search fallback
            has_coord = bool(re.search(
                r"\bcoordination\s+of\s+care\b|\brelease\s+of\s+information\b|\broi\b"
                r"|\bcollateral\s+contact\b|\bcontacted\s+(?:doctor|provider|therapist|pcp)\b",
                note.full_text,
                re.IGNORECASE,
            ))

        # For progress notes: conditional — only required if coordination occurred
        if note.note_type == "progress":
            if not has_coord:
                return not_applicable("I1", "Progress note: no coordination of care reference — conditional check N/A.")

        if not has_coord:
            # Check for refusal
            if RE_REFUSAL.search(note.full_text):
                if RE_REFUSAL_REASON.search(note.full_text):
                    return passed("I1", "Member refused coordination of care; refusal and reason documented.")
                return failed("I1", "Member refusal of coordination noted but reason not documented.")
            return failed("I1", "No coordination of care documentation found.")

        return passed("I1", "Coordination of care documented.", excerpts=[coord_text[:200]] if coord_text else [])


class CheckI2:
    """Coordination at key milestones (intake, discharge, level-of-care transition)."""
    standard_id = "I2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in ("intake", "consultation", "discharge"):
            return not_applicable("I2")

        milestone_map = {
            "intake": "at the time of intake",
            "discharge": "at the time of discharge",
            "consultation": "at the point of level-of-care transition",
        }
        milestone = milestone_map[note.note_type]

        coord_text = get_section(note.sections, "coordination") or note.full_text[:4000]
        has_coord = bool(re.search(
            r"\bcoordination\s+of\s+care\b|\brelease\s+of\s+information\b|\broi\b"
            r"|\bcollateral\b|\bcontacted\b",
            coord_text,
            re.IGNORECASE,
        ))

        if has_coord:
            return passed("I2", f"Coordination of care documented at {milestone}.")

        answer = judge.evaluate(
            question=(
                f"Does this {note.note_type} note document coordination of care "
                f"activities ({milestone})?"
            ),
            context=coord_text[:3000],
        )
        return CheckResult(
            standard_id="I2",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )
