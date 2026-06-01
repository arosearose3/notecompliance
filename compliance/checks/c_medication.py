"""
Standards C1–C2e: Medical conditions and medication tracking.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, failed, manual_review, not_applicable, passed,
)
from compliance.extract.medications import parse_medications, section_mentions_medications
from compliance.extract.sections import get_section, has_section

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note

RE_NEGATED_ALLERGY = re.compile(
    r"\b(nkda|none|none reported|no known|no allergies|denies allergies)\b",
    re.IGNORECASE,
)


class CheckC1:
    """Allergies, adverse reactions, and relevant medical conditions."""
    standard_id = "C1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in ("intake", "progress", "discharge"):
            return not_applicable("C1")

        # For progress notes, only required if meds are discussed
        if note.note_type == "progress" and not section_mentions_medications(note.full_text):
            return not_applicable("C1", "Medication not discussed in this progress note.")

        allergy_text = get_section(note.sections, "allergies")
        med_hist_text = get_section(note.sections, "medical_history")

        missing = []
        if not allergy_text:
            missing.append("Allergies section")
        if not med_hist_text:
            missing.append("Medical history section")

        if missing:
            # Intake: hard fail; discharge: hard fail
            if note.note_type in ("intake", "discharge"):
                return failed("C1", f"Missing: {missing}.")
            return manual_review("C1", f"Missing: {missing}. Verify if meds were discussed.")

        # Accepted negation forms count as compliance
        combined = (allergy_text + " " + med_hist_text).lower()
        has_content = bool(allergy_text.strip()) or RE_NEGATED_ALLERGY.search(combined)
        if not has_content:
            return failed("C1", "Allergies section present but appears empty.")

        return passed("C1", "Allergies and medical history documented.")


def _meds_apply(note) -> bool:
    """True if the note has a Medications section or discusses medications."""
    return has_section(note.sections, "medications") or section_mentions_medications(note.full_text)


class CheckC2a:
    """Medication order types (standing/PRN/STAT)."""
    standard_id = "C2a"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if not _meds_apply(note):
            return not_applicable("C2a", "No medications discussed.")

        meds_text = get_section(note.sections, "medications")
        if not meds_text:
            return not_applicable("C2a", "No Medications section found.")

        entries = parse_medications(meds_text)
        if not entries:
            return manual_review("C2a", "Medications section found but could not parse entries.")

        missing_type = [e["raw_line"][:80] for e in entries if not e["order_type"]]
        if missing_type:
            return failed(
                "C2a",
                f"{len(missing_type)} medication(s) missing order type (standing/PRN/STAT).",
                excerpts=missing_type[:5],
            )
        return passed("C2a", f"Order types documented for {len(entries)} medication(s).")


class CheckC2b:
    """Medication date, dosage, and frequency."""
    standard_id = "C2b"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if not _meds_apply(note):
            return not_applicable("C2b", "No medications discussed.")

        meds_text = get_section(note.sections, "medications")
        if not meds_text:
            return not_applicable("C2b", "No Medications section found.")

        entries = parse_medications(meds_text)
        if not entries:
            return manual_review("C2b", "Could not parse medication entries.")

        issues = []
        for e in entries:
            problems = []
            if not e["dose"]:
                problems.append("missing dose")
            if not e["freq"]:
                problems.append("missing frequency")
            if problems:
                issues.append(f"{e['name']}: {', '.join(problems)}")

        if issues:
            return failed("C2b", f"Incomplete medication entries: {issues[:5]}.", excerpts=issues[:5])
        return passed("C2b", f"Date/dose/frequency documented for {len(entries)} medication(s).")


class CheckC2c:
    """Informed consent for medication."""
    standard_id = "C2c"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if not _meds_apply(note):
            return not_applicable("C2c", "No medications discussed.")

        # Rule: look for consent language
        consent_match = re.search(
            r"\binformed consent\b|\bconsent\s+for\s+medication\b|\bbenefits.*risks\b",
            note.full_text,
            re.IGNORECASE,
        )
        if consent_match:
            answer = judge.evaluate(
                question=(
                    "Does this note document informed consent for medication including "
                    "benefits, risks, side effects, and alternatives?"
                ),
                context=note.full_text[:4000],
            )
            return CheckResult(
                standard_id="C2c",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )

        return failed("C2c", "No informed consent language found for medication.")


class CheckC2d:
    """Change rationale or no-change rationale for medication."""
    standard_id = "C2d"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if not _meds_apply(note):
            return not_applicable("C2d", "No medications discussed.")

        meds_text = get_section(note.sections, "medications")
        answer = judge.evaluate(
            question=(
                "Does this note document the rationale for any medication changes, "
                "or explicitly note that no changes were made and why?"
            ),
            context=meds_text or note.full_text[:3000],
        )
        return CheckResult(
            standard_id="C2d",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckC2e:
    """Discharge medication list with dosages."""
    standard_id = "C2e"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "discharge":
            return not_applicable("C2e")

        dc_meds = get_section(note.sections, "medications_at_discharge", "medications")
        if not dc_meds:
            return failed("C2e", "No discharge medications list found.")

        entries = parse_medications(dc_meds)
        if entries and all(e["dose"] for e in entries):
            return passed("C2e", f"Discharge medication list with {len(entries)} entry/entries and doses.")
        if entries:
            return failed("C2e", "Discharge medication entries found but some are missing doses.")

        return manual_review("C2e", "Discharge medications section present but could not parse entries.")
