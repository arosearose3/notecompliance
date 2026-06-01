"""
Standards A1–A5: Identification and per-encounter metadata.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, failed, not_applicable, passed, manual_review,
)
from compliance.extract.sections import has_section, get_section

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note

# CPT codes for group therapy
GROUP_CPT = frozenset(["90853", "90849", "90857"])
# CPT codes for family therapy
FAMILY_CPT = frozenset(["90847", "90846", "90849"])

RE_RELATIONSHIP = re.compile(
    r"\((mother|father|spouse|partner|sibling|sister|brother|child|son|"
    r"daughter|guardian|parent|husband|wife|caregiver|grandparent)\)",
    re.IGNORECASE,
)

KNOWN_DEGREES = frozenset([
    "licensed professional counselor",
    "licensed clinical social worker",
    "licensed marriage and family therapist",
    "licensed psychologist",
    "psychiatrist",
    "licensed addiction counselor",
    "registered nurse",
    "nurse practitioner",
    "physician assistant",
    "md", "do", "phd", "psyd",
])

RE_DSM_CODE = re.compile(r"\b[FfZz]\d{2}(?:\.\d+)?\b")


class CheckA1:
    """Member name or ID on each page."""
    standard_id = "A1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        member = note.header.member_name
        if not member:
            return failed("A1", "Member name not extractable from note header.")

        failing_pages = []
        for page in note.pages:
            if member.lower() not in page.text.lower():
                failing_pages.append(page.page_num_in_note)

        if failing_pages:
            return failed(
                "A1",
                f"Member identifier missing on page(s): {failing_pages}.",
                pages=failing_pages,
            )
        return passed("A1", f"Member '{member}' found on all {len(note.pages)} page(s).")


class CheckA2:
    """Demographics, contacts, consent forms, guardianship."""
    standard_id = "A2"

    _REQUIRED = [
        ("address",          "Address"),
        ("phone",            "Phone / contact numbers"),
        ("emergency_contact","Emergency contact"),
        ("marital_status",   "Marital/legal status"),
        ("consent",          "Consent form"),
    ]

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("A2")

        missing = []
        for canon, label in self._REQUIRED:
            if not has_section(note.sections, canon):
                missing.append(label)

        if missing:
            return failed("A2", f"Missing demographics sub-items: {missing}.")
        return passed("A2", "All required demographics/consent sub-items present.")


class CheckA3:
    """Per-encounter metadata: date, duration, attendees, diagnosis, service code, clinician."""
    standard_id = "A3"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        h = note.header
        missing = []

        if not h.service_date:
            missing.append("date of service")
        if h.duration_minutes is None and not (h.start_time and h.end_time):
            missing.append("duration / start-stop time")
        if not h.participants:
            missing.append("session attendees/participants")
        if not has_section(note.sections, "diagnosis"):
            # fallback: look for any DSM code anywhere in the note
            if not RE_DSM_CODE.search(note.full_text):
                missing.append("diagnosis")
        if not h.service_code:
            missing.append("service code")
        if not h.clinician:
            missing.append("clinician name")
        if not h.clinician_credential:
            missing.append("clinician credential/degree")
        if not h.license_id:
            missing.append("license ID")

        if missing:
            return failed("A3", f"Missing encounter metadata: {missing}.")
        return passed("A3", "Encounter metadata complete.")


class CheckA4:
    """Group session: subject/topic must be documented."""
    standard_id = "A4"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        code = note.header.service_code or ""
        is_group = (note.note_type == "group") or (code in GROUP_CPT)
        if not is_group:
            return not_applicable("A4", "Not a group session note.")

        topic = get_section(note.sections, "topic")
        if topic:
            return passed("A4", "Group session topic documented.", excerpts=[topic[:200]])

        # Judge for free-text topic buried in body
        answer = judge.evaluate(
            question="Does this group therapy note document the topic or subject covered in the session?",
            context=note.full_text[:3000],
        )
        return CheckResult(
            standard_id="A4",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckA5:
    """Family session: attendees and relationships must be documented."""
    standard_id = "A5"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        code = note.header.service_code or ""
        is_family = (note.note_type == "family") or (code in FAMILY_CPT)
        if not is_family:
            return not_applicable("A5", "Not a family session note.")

        participants_text = get_section(note.sections, "participants")
        if not participants_text:
            participants_text = " ".join(note.header.participants)

        rel_matches = RE_RELATIONSHIP.findall(participants_text)
        if len(note.header.participants) >= 2 and rel_matches:
            return passed(
                "A5",
                f"Family attendees with relationships documented: {rel_matches}.",
                excerpts=[participants_text[:200]],
            )

        answer = judge.evaluate(
            question=(
                "Does this family therapy note list all attendees "
                "and their relationship to each other?"
            ),
            context=participants_text or note.full_text[:2000],
        )
        return CheckResult(
            standard_id="A5",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )
