"""
Standards F1–F8: Progress note elements.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, failed, manual_review, not_applicable, passed,
)
from compliance.extract.sections import get_section, has_section
from compliance.extract.signature import extract_signature

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note

# CPT codes that are time-based (require start/stop or total duration)
TIME_BASED_CPT = frozenset(["90832", "90834", "90837", "90847", "90846",
                             "90853", "90791", "90792"])

# Telehealth modifier patterns and service codes
TELEHEALTH_MODS = re.compile(r"\b(GT|GQ|95|02|10|93)\b")
TELEHEALTH_KEYWORDS = re.compile(
    r"\btelehealth\b|\bteletherapy\b|\bvideo\b|\bonline\b|\bvirtual\b"
    r"|\baudio[\s\-]only\b|\bphone\b|\btelemedicine\b",
    re.IGNORECASE,
)
TELEHEALTH_LOCATIONS = re.compile(
    r"\blocation:\s*(?:home|telehealth|virtual|remote|phone|video)\b",
    re.IGNORECASE,
)

OUTREACH_KEYWORDS = re.compile(
    r"\bcalled?\b|\btexted?\b|\bvoicemail\b|\boutreach\b|\bleft\s+message\b"
    r"|\batttempted\s+contact\b|\bcontact\s+attempt\b",
    re.IGNORECASE,
)

MISSED_APPT_KEYWORDS = re.compile(
    r"\bno[\s\-]show\b|\bmissed\s+appointment\b|\bcancelled\b|\bcanceled\b"
    r"|\bdid\s+not\s+attend\b|\bdna\b",
    re.IGNORECASE,
)

_PROGRESS_TYPES = frozenset(["progress", "group", "family"])


class CheckF1:
    """Signature of the rendering clinician."""
    standard_id = "F1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in (*_PROGRESS_TYPES, "discharge"):
            return not_applicable("F1")

        sig = extract_signature(note.last_page_text)
        if sig:
            return passed(
                "F1",
                f"Signature found: {sig['name']}, {sig['credential']}.",
                excerpts=[str(sig)],
            )
        # Fallback: look for "signed" anywhere on last page
        if re.search(r"\bsigned\s+this\s+note\b|\belectronically\s+signed\b", note.last_page_text, re.IGNORECASE):
            return passed("F1", "Signature statement found on last page.")

        return failed("F1", "No clinician signature block found on last page.")


class CheckF2:
    """Date of service."""
    standard_id = "F2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.header.service_date:
            return passed("F2", f"Date of service: {note.header.service_date}.")
        return failed("F2", "Date of service not found in note header.")


class CheckF3:
    """Telehealth documentation when service delivered remotely."""
    standard_id = "F3"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        is_telehealth = (
            TELEHEALTH_LOCATIONS.search(note.full_text)
            or (note.header.service_code and TELEHEALTH_MODS.search(note.header.service_code))
        )

        if not is_telehealth:
            # Check for telehealth keywords suggesting it may be remote
            if TELEHEALTH_KEYWORDS.search(note.full_text):
                return passed("F3", "Telehealth/remote delivery documented in note body.")
            return not_applicable("F3", "No indication this was a telehealth session.")

        # Confirmed or suspected telehealth — verify documentation
        if TELEHEALTH_KEYWORDS.search(note.full_text):
            return passed("F3", "Telehealth service delivery documented.")

        return failed(
            "F3",
            "Location or service code suggests telehealth but note body does not "
            "document remote service delivery (video, phone, telehealth, etc.).",
        )


class CheckF4:
    """Member strengths and limitations toward goals."""
    standard_id = "F4"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in _PROGRESS_TYPES:
            return not_applicable("F4")

        has_strengths = has_section(note.sections, "strengths")
        has_limitations = has_section(note.sections, "limitations")

        if has_strengths and has_limitations:
            return passed("F4", "Strengths and limitations/barriers sections present.")

        missing = []
        if not has_strengths:
            missing.append("strengths")
        if not has_limitations:
            missing.append("limitations/barriers")

        # Keyword fallback
        keyword_hit = bool(re.search(
            r"\bstrengths?\b.*\blimitations?\b|\bbarriers?\b.*\bstrengths?\b",
            note.full_text,
            re.IGNORECASE | re.DOTALL,
        ))
        if keyword_hit:
            return passed("F4", "Strengths and limitations referenced in note body.")

        answer = judge.evaluate(
            question=(
                "Does this progress note document the member's strengths "
                "and limitations/barriers in achieving treatment plan goals?"
            ),
            context=note.full_text[:4000],
        )
        return CheckResult(
            standard_id="F4",
            verdict=answer.verdict,
            rationale=f"Missing sections: {missing}. {answer.rationale}",
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckF5:
    """Interventions consistent with treatment-plan goals."""
    standard_id = "F5"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in _PROGRESS_TYPES:
            return not_applicable("F5")

        intervention_text = get_section(note.sections, "interventions")
        if not intervention_text:
            # Keyword anywhere in note
            if not re.search(r"\bintervention\b|\btherapeutic\b|\btechnique\b|\bCBT\b|\bDBT\b", note.full_text, re.IGNORECASE):
                return failed("F5", "No interventions documented in progress note.")
            intervention_text = note.full_text[:3000]

        # Cross-note check with treatment plan
        if bundle:
            tp_notes = bundle.of_type("treatment_plan")
            if tp_notes:
                goals_text = get_section(tp_notes[0].sections, "goals") or ""
                answer = judge.evaluate(
                    question=(
                        "Are the interventions in this progress note consistent with "
                        "the goals/objectives documented in the treatment plan?"
                    ),
                    context=f"Progress note interventions:\n{intervention_text}\n\nTreatment plan goals:\n{goals_text}",
                )
                return CheckResult(
                    standard_id="F5",
                    verdict=answer.verdict,
                    rationale=answer.rationale,
                    excerpts=tuple(answer.excerpts),
                    judge_used=judge.name,
                )

        return manual_review(
            "F5",
            "Interventions documented but treatment plan not available for cross-note "
            "alignment check. Verify manually.",
        )


class CheckF6:
    """Follow-up dates documented."""
    standard_id = "F6"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in _PROGRESS_TYPES:
            return not_applicable("F6")

        fu_text = get_section(note.sections, "follow_up")
        if fu_text:
            return passed("F6", "Follow-up documented.", excerpts=[fu_text[:100]])

        # Look for a date pattern after "next" or "follow"
        match = re.search(
            r"(?:next|follow[\s\-]up|scheduled)[^.]*\d{1,2}/\d{1,2}/\d{2,4}",
            note.full_text,
            re.IGNORECASE,
        )
        if match:
            return passed("F6", "Follow-up date reference found.", excerpts=[match.group()])

        return failed("F6", "No follow-up date documented.")


class CheckF7:
    """Missed appointments — outreach attempt must be documented."""
    standard_id = "F7"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in _PROGRESS_TYPES:
            return not_applicable("F7")

        is_missed = bool(MISSED_APPT_KEYWORDS.search(note.full_text))
        if not is_missed:
            return not_applicable("F7", "No missed/cancelled appointment indicated.")

        has_outreach = bool(OUTREACH_KEYWORDS.search(note.full_text))
        if has_outreach:
            return passed("F7", "Outreach attempt documented for missed appointment.")

        return failed(
            "F7",
            "Missed/cancelled appointment noted but no outreach attempt documented.",
        )


class CheckF8:
    """Time-based service — start/stop time or total duration required."""
    standard_id = "F8"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        code = note.header.service_code or ""
        is_time_based = (
            code in TIME_BASED_CPT
            or note.note_type in _PROGRESS_TYPES
        )
        if not is_time_based:
            return not_applicable("F8")

        has_duration = note.header.duration_minutes is not None
        has_times = note.header.start_time and note.header.end_time

        if has_duration or has_times:
            detail = (
                f"{note.header.duration_minutes} minutes" if has_duration
                else f"{note.header.start_time}–{note.header.end_time}"
            )
            return passed("F8", f"Time documented: {detail}.")

        return failed("F8", "Time-based service but duration/start-stop times not found.")
