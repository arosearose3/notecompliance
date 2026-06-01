"""
Standards D1–D9: Assessment content (primarily intake notes).
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

RE_DSM_CODE = re.compile(r"\b[FfZz]\d{2}(?:\.\d+)?\b")

RISK_KEYWORDS = {
    "suicidal ideation":       re.compile(r"\bsuicid(?:al|e|ality)\b|\bsi\b", re.IGNORECASE),
    "homicidal ideation":      re.compile(r"\bhomicid(?:al|e)\b|\bhi\b", re.IGNORECASE),
    "self-injurious behavior": re.compile(r"\bself[\s\-]injur|\bnsi[b]?\b|\bcutting\b|\bself[\s\-]harm\b", re.IGNORECASE),
    "elopement risk":          re.compile(r"\belopement\b|\brun\s*away\b|\bescape\b", re.IGNORECASE),
    "imminent risk of harm":   re.compile(r"\bimminent\s+risk\b|\bdanger\s+to\s+(self|others)\b", re.IGNORECASE),
}

RE_EXPLICIT_DENIAL = re.compile(
    r"\bdenies?\b|\bno\s+(?:current|active|known)?\b|\bnot\s+present\b|\bnone\b|\bnegative\b",
    re.IGNORECASE,
)

RE_SUBSTANCE_CATEGORIES = {
    "nicotine":  re.compile(r"\bnicotine\b|\btobacco\b|\bcigarette\b|\bsmoking\b", re.IGNORECASE),
    "alcohol":   re.compile(r"\balcohol\b|\bdrinking\b|\betoh\b", re.IGNORECASE),
    "illicit":   re.compile(r"\billicit\b|\bdrugs?\b|\bmarijuana\b|\bcannabis\b|\bcocaine\b|\bheroin\b|\bmeth\b", re.IGNORECASE),
    "rx":        re.compile(r"\bprescription\b|\bprescribed\b|\brx\b", re.IGNORECASE),
    "otc":       re.compile(r"\bover[\s\-]the[\s\-]counter\b|\botc\b", re.IGNORECASE),
}


class CheckD1:
    """Presenting problems, MSE, psychosocial conditions, and information source."""
    standard_id = "D1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in ("intake", "consultation"):
            return not_applicable("D1")

        missing = []
        if not has_section(note.sections, "presenting_problem"):
            missing.append("Presenting Problem section")
        if not has_section(note.sections, "mse"):
            missing.append("Mental Status Exam section")
        if not has_section(note.sections, "psychosocial_history"):
            missing.append("Psychosocial/Social History section")

        if missing:
            return failed("D1", f"Missing required assessment sections: {missing}.")

        mse_text = get_section(note.sections, "mse")
        pp_text = get_section(note.sections, "presenting_problem")
        answer = judge.evaluate(
            question=(
                "Does the Mental Status Exam cover the standard MSE dimensions "
                "(appearance, behaviour, speech, mood, affect, thought process, "
                "thought content, perception, cognition, insight, judgment)? "
                "Does the presenting problem identify the information source?"
            ),
            context=f"MSE:\n{mse_text}\n\nPresenting Problem:\n{pp_text}",
        )
        return CheckResult(
            standard_id="D1",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckD2:
    """Special status assessment: SI/HI/SIB/elopement/imminent harm must be explicitly assessed."""
    standard_id = "D2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type not in ("intake", "progress", "consultation"):
            return not_applicable("D2")

        risk_text = get_section(note.sections, "special_status") or note.full_text
        missing_categories = []

        for category, pattern in RISK_KEYWORDS.items():
            if not pattern.search(risk_text):
                missing_categories.append(category)

        if not missing_categories:
            return passed("D2", "All special status categories addressed.")

        # If we found some but not all, that's a partial fail
        if len(missing_categories) == len(RISK_KEYWORDS):
            return failed("D2", "No special status risk categories addressed (SI/HI/SIB/elopement/harm).")

        return failed(
            "D2",
            f"Special status assessment missing categories: {missing_categories}.",
            excerpts=[risk_text[:300]],
        )


class CheckD3:
    """Medical and psychiatric history."""
    standard_id = "D3"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D3")

        psych_hist = get_section(note.sections, "psychiatric_history")
        med_hist = get_section(note.sections, "medical_history")

        if not psych_hist and not med_hist:
            return failed("D3", "Neither psychiatric nor medical history sections found.")

        answer = judge.evaluate(
            question=(
                "Do the psychiatric and medical history sections document: "
                "(1) previous treatment dates, (2) prior clinician/facility names, "
                "(3) prior interventions and responses, (4) information sources, "
                "(5) relevant family history?"
            ),
            context=f"Psychiatric History:\n{psych_hist}\n\nMedical History:\n{med_hist}",
        )
        return CheckResult(
            standard_id="D3",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckD4:
    """Behavioral health history — history of abuse."""
    standard_id = "D4"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D4")

        abuse_text = get_section(note.sections, "abuse_history") or ""
        full = (abuse_text + " " + note.full_text[:5000]).lower()

        presence = bool(re.search(r"\babuse\b|\btrauma\b|\bneglect\b|\bvictim\b", full, re.IGNORECASE))
        denial = bool(re.search(r"\bdenies?\b|\bno\s+(?:history\s+of\s+)?abuse\b|\bno\s+trauma\b", full, re.IGNORECASE))

        if presence or denial:
            return passed("D4", "Abuse/trauma history explicitly assessed.")

        return failed("D4", "No explicit assessment or denial of abuse/trauma history found.")


class CheckD5:
    """Adolescent sexual behavior history (ages 12–17)."""
    standard_id = "D5"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D5")

        dob = note.header.member_dob
        svc = note.header.service_date
        if not dob or not svc:
            return manual_review("D5", "Member DOB not found — cannot determine if adolescent age range applies.")

        from datetime import date
        age = (svc - dob).days // 365
        if age < 12 or age >= 18:
            return not_applicable("D5", f"Member age {age} — adolescent sexual history check N/A.")

        sex_hist = get_section(note.sections, "sexual_history")
        if sex_hist:
            return passed("D5", "Sexual behavior history section present.")

        answer = judge.evaluate(
            question="Does this intake note include a sexual behavior history for this adolescent member?",
            context=note.full_text[:4000],
        )
        return CheckResult(
            standard_id="D5",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckD6:
    """Child/adolescent prenatal, perinatal, and developmental history."""
    standard_id = "D6"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D6")

        dob = note.header.member_dob
        svc = note.header.service_date
        if not dob or not svc:
            return manual_review("D6", "Member DOB not found — cannot determine if child/adolescent.")

        from datetime import date
        age = (svc - dob).days // 365
        if age >= 18:
            return not_applicable("D6", f"Member age {age} — developmental history check N/A.")

        dev_text = get_section(note.sections, "developmental_history")
        if not dev_text:
            return failed("D6", "Developmental history section not found for child/adolescent member.")

        answer = judge.evaluate(
            question=(
                "Does the developmental history cover: "
                "(1) prenatal/perinatal events, "
                "(2) physical development, (3) psychological development, "
                "(4) social development, (5) intellectual and academic history?"
            ),
            context=dev_text,
        )
        return CheckResult(
            standard_id="D6",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckD7:
    """12+ substance use history."""
    standard_id = "D7"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D7")

        dob = note.header.member_dob
        svc = note.header.service_date
        if not dob or not svc:
            return manual_review("D7", "Member DOB not found — cannot confirm age ≥ 12.")

        from datetime import date
        age = (svc - dob).days // 365
        if age < 12:
            return not_applicable("D7", f"Member age {age} — substance use history N/A.")

        sub_text = get_section(note.sections, "substance_use") or note.full_text

        missing_categories = [
            cat for cat, pat in RE_SUBSTANCE_CATEGORIES.items()
            if not pat.search(sub_text)
        ]

        if not missing_categories:
            return passed("D7", "All five substance use categories addressed.")

        answer = judge.evaluate(
            question=(
                "Does this note address substance use history covering "
                "nicotine, alcohol, illicit drugs, prescription medications, "
                "and over-the-counter medications (present or explicitly denied)?"
            ),
            context=sub_text[:3000],
        )
        return CheckResult(
            standard_id="D7",
            verdict=answer.verdict,
            rationale=f"Missing categories by keyword: {missing_categories}. {answer.rationale}",
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckD8:
    """DSM diagnosis consistent with the assessment."""
    standard_id = "D8"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D8")

        diag_text = get_section(note.sections, "diagnosis")
        if not diag_text:
            if not RE_DSM_CODE.search(note.full_text):
                return failed("D8", "No diagnosis section or DSM code found.")
            diag_text = ""

        # Rule: code format present
        code_match = RE_DSM_CODE.search(diag_text or note.full_text)
        if not code_match:
            return failed("D8", "Diagnosis section found but no DSM/ICD code format detected.")

        # Judge: alignment with assessment
        pp_text = get_section(note.sections, "presenting_problem")
        mse_text = get_section(note.sections, "mse")
        answer = judge.evaluate(
            question=(
                "Is the documented diagnosis consistent with and supported by "
                "the presenting problem, MSE, and assessment data in this note?"
            ),
            context=(
                f"Diagnosis:\n{diag_text}\n\n"
                f"Presenting Problem:\n{pp_text}\n\n"
                f"MSE:\n{mse_text}"
            ),
        )
        return CheckResult(
            standard_id="D8",
            verdict=answer.verdict,
            rationale=answer.rationale,
            excerpts=tuple(answer.excerpts),
            judge_used=judge.name,
        )


class CheckD9:
    """Functional impairment documentation."""
    standard_id = "D9"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        if note.note_type != "intake":
            return not_applicable("D9")

        fi_text = get_section(note.sections, "functional_impairment")
        if fi_text:
            return passed("D9", "Functional impairment section present.", excerpts=[fi_text[:200]])

        # Fallback: keyword in body
        match = re.search(
            r"\bfunctional\s+impairment\b|\bimpact\s+on\s+functioning\b|\bgaf\b|\bwhodas\b",
            note.full_text,
            re.IGNORECASE,
        )
        if match:
            answer = judge.evaluate(
                question=(
                    "Does this note document functional impairment or the impact of "
                    "mental health on daily functioning?"
                ),
                context=note.full_text[:4000],
            )
            return CheckResult(
                standard_id="D9",
                verdict=answer.verdict,
                rationale=answer.rationale,
                excerpts=tuple(answer.excerpts),
                judge_used=judge.name,
            )

        return failed("D9", "No functional impairment section or keyword found.")
