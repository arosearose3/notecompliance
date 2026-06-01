"""
Standards E1–E10: Treatment plan elements.
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

RE_DATE_PHRASE = re.compile(
    r"\bby\s+\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\bwithin\s+\d+\s+(?:days?|weeks?|months?)\b"
    r"|\bin\s+\d+\s+(?:days?|weeks?|months?)\b"
    r"|\bby\s+(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b",
    re.IGNORECASE,
)

RE_LOC = re.compile(
    r"\b(outpatient|iop|php|intensive outpatient|partial hospital|inpatient|"
    r"residential|detox|day treatment|telehealth)\b",
    re.IGNORECASE,
)

RE_PROGRESS_ANNOTATION = re.compile(
    r"\b(progress(?:ing)?|improved?|met goal|not met|no progress|stagnant|"
    r"continuing|maintained|achieved|not achieved|partially met)\b",
    re.IGNORECASE,
)

RE_DEFERRED = re.compile(r"\bdeferred\b|\bpostponed\b|\bnot\s+addressed\b", re.IGNORECASE)
RE_MEASURABLE = re.compile(
    r"\b(\d+%|times?\s+per\s+week|\d+\s+out\s+of\s+\d+|scale\s+of|\bscore\b"
    r"|reduce|increase|decrease|improve\s+from|from\s+\d+\s+to\s+\d+)\b",
    re.IGNORECASE,
)


class CheckE1:
    """Specific symptoms and problems tied to diagnosis."""
    standard_id = "E1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E1")

        probs = get_section(note.sections, "problems")
        if not probs:
            return failed("E1", "No Problems/Target Symptoms section found in treatment plan.")

        return passed("E1", "Problems section present.", excerpts=[probs[:200]])


class CheckE2:
    """Prioritisation — problems ordered; deferred items labelled."""
    standard_id = "E2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E2")

        probs = get_section(note.sections, "problems")
        if not probs:
            return failed("E2", "No Problems section found; cannot assess prioritisation.")

        # Check for numbering or deferred labels
        numbered = bool(re.search(r"^\s*\d+[\.\)]\s+", probs, re.MULTILINE))
        has_deferred = bool(RE_DEFERRED.search(probs))

        if not numbered:
            answer = judge.evaluate(
                question=(
                    "Are treatment problems prioritised (ordered by importance)? "
                    "Are any deferred problems explicitly labelled as deferred?"
                ),
                context=probs,
            )
            return CheckResult(
                standard_id="E2",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )

        return passed("E2", "Problems appear numbered; prioritisation present.")


class CheckE3:
    """Recommended level of care relates to impairment."""
    standard_id = "E3"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E3")

        loc_text = get_section(note.sections, "level_of_care") or note.full_text[:4000]
        loc_match = RE_LOC.search(loc_text)
        if not loc_match:
            return failed("E3", "No level of care identified in treatment plan.")

        impairment_ref = bool(re.search(
            r"\bimpair|\bfunctioning\b|\bseverity\b|\bsymptoms?\b",
            loc_text, re.IGNORECASE,
        ))
        if not impairment_ref:
            return failed("E3", f"Level of care '{loc_match.group()}' identified but no impairment rationale found.")

        answer = judge.evaluate(
            question=(
                "Does the treatment plan link the recommended level of care to "
                "the member's level of functional impairment?"
            ),
            context=loc_text[:2000],
        )
        return CheckResult(
            standard_id="E3",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckE4:
    """Member (and family where applicable) involvement in treatment planning."""
    standard_id = "E4"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E4")

        involvement_text = get_section(note.sections, "member_involvement") or ""
        keyword_match = bool(re.search(
            r"\bmember\s+(?:participated|agreed?|involved|reviewed|signed|consented)\b"
            r"|\bpatient\s+(?:participated|agreed?|involved|reviewed|signed|consented)\b"
            r"|\bconsumer\s+(?:participated|agreed?|involved)\b",
            (involvement_text or note.full_text[:3000]),
            re.IGNORECASE,
        ))

        if not keyword_match:
            answer = judge.evaluate(
                question=(
                    "Does this treatment plan document that the member (and family "
                    "where indicated) participated in or agreed to the treatment plan?"
                ),
                context=note.full_text[:4000],
            )
            return CheckResult(
                standard_id="E4",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )

        return passed("E4", "Member involvement in planning documented.")


class CheckE5:
    """SMART goals: specific, behavioural, measurable, realistic."""
    standard_id = "E5"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E5")

        goals_text = get_section(note.sections, "goals")
        if not goals_text:
            return failed("E5", "No goals section found.")

        # Heuristic: measurable language present
        if not RE_MEASURABLE.search(goals_text):
            # No heuristic evidence — send to judge
            answer = judge.evaluate(
                question=(
                    "Are treatment goals specific, behavioral, measurable, and realistic? "
                    "For each goal, note which SMART criteria are met and which are missing."
                ),
                context=goals_text[:3000],
            )
            return CheckResult(
                standard_id="E5",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )

        # Measurable language found — still send to judge for full SMART evaluation
        answer = judge.evaluate(
            question=(
                "Rate whether treatment goals meet all SMART criteria "
                "(specific, behavioral, measurable, realistic). "
                "Note any dimensions that are missing."
            ),
            context=goals_text[:3000],
        )
        return CheckResult(
            standard_id="E5",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckE6:
    """Goal time frames."""
    standard_id = "E6"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E6")

        goals_text = get_section(note.sections, "goals")
        if not goals_text:
            return failed("E6", "No goals section found.")

        if RE_DATE_PHRASE.search(goals_text):
            return passed("E6", "Time frame language found in goals.", excerpts=[goals_text[:200]])

        return failed("E6", "No time frame (target date or duration) found in goals.")


class CheckE7:
    """Progress or lack of progress toward goals (for treatment plan updates)."""
    standard_id = "E7"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E7")

        goals_text = get_section(note.sections, "goals") or note.full_text
        if RE_PROGRESS_ANNOTATION.search(goals_text):
            return passed("E7", "Progress annotations found for goals.")

        answer = judge.evaluate(
            question=(
                "Does this treatment plan document progress or lack of progress "
                "toward each treatment goal?"
            ),
            context=goals_text[:3000],
        )
        return CheckResult(
            standard_id="E7",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckE8:
    """Rationale for estimated treatment length."""
    standard_id = "E8"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E8")

        los_text = get_section(note.sections, "treatment_length")
        if not los_text:
            # Check for inline reference
            match = re.search(
                r"\b(?:estimated?\s+)?(?:length\s+of\s+treatment|treatment\s+duration"
                r"|episode\s+length|estimated\s+duration)\b[^.]*\.",
                note.full_text,
                re.IGNORECASE,
            )
            if not match:
                return failed("E8", "No treatment length/duration rationale found.")
            los_text = match.group()

        answer = judge.evaluate(
            question=(
                "Does this section explain the rationale for the estimated treatment "
                "length (not just state a number, but explain why)?"
            ),
            context=los_text,
        )
        return CheckResult(
            standard_id="E8",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckE9:
    """Updates on goal achievement or new problems (treatment plan revisions)."""
    standard_id = "E9"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E9")

        # Look for revision/update metadata
        has_update = bool(re.search(
            r"\bplan\s+(?:updated|revised|modified)\b|\bgoal\s+(?:achieved|met|modified)\b"
            r"|\bnew\s+problem\b|\badded\b",
            note.full_text,
            re.IGNORECASE,
        ))
        if not has_update:
            answer = judge.evaluate(
                question=(
                    "Does this treatment plan update document newly achieved goals, "
                    "modified goals, or newly identified problems?"
                ),
                context=note.full_text[:4000],
            )
            return CheckResult(
                standard_id="E9",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )
        return passed("E9", "Treatment plan update/revision language found.")


class CheckE10:
    """Re-evaluation when progress stalls."""
    standard_id = "E10"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "treatment_plan":
            return not_applicable("E10")

        stagnation = bool(re.search(
            r"\bno\s+progress\b|\bstagnant\b|\bnot\s+(?:met|progressing|improving)\b"
            r"|\black\s+of\s+progress\b",
            note.full_text,
            re.IGNORECASE,
        ))

        if not stagnation:
            return not_applicable("E10", "No evidence of stalled progress — re-evaluation check N/A.")

        modified = bool(re.search(
            r"\bmodified?\b|\brevised?\b|\bupdated?\b|\bnew\s+(?:goal|intervention|approach)\b",
            note.full_text,
            re.IGNORECASE,
        ))
        if modified:
            return passed("E10", "Stalled progress noted and plan appears modified.")

        answer = judge.evaluate(
            question=(
                "This treatment plan notes lack of progress. Does it re-evaluate "
                "goals and/or modify interventions in response?"
            ),
            context=note.full_text[:4000],
        )
        return CheckResult(
            standard_id="E10",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )
