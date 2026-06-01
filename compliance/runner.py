"""
Runner — orchestrates ingest → classify → checks → NoteReport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from compliance import applicability
from compliance.checks.base import CheckResult, not_applicable
from compliance.checks import (
    a_identification, b_entry, c_medication, d_assessment,
    e_treatment_plan, f_progress, g_discharge_planning,
    h_discharge_summary, i_coordination, j_referrals, k_telehealth,
)
from compliance.ingest import ingest_directory, split_notes
from compliance.judges.null import NullJudge
from compliance.models import ContextBundle, Note

if TYPE_CHECKING:
    from compliance.judges.base import Judge

# ── Check registry ────────────────────────────────────────────────────────────

ALL_CHECKS = [
    a_identification.CheckA1(),
    a_identification.CheckA2(),
    a_identification.CheckA3(),
    a_identification.CheckA4(),
    a_identification.CheckA5(),
    b_entry.CheckB1(),
    b_entry.CheckB2(),
    c_medication.CheckC1(),
    c_medication.CheckC2a(),
    c_medication.CheckC2b(),
    c_medication.CheckC2c(),
    c_medication.CheckC2d(),
    c_medication.CheckC2e(),
    d_assessment.CheckD1(),
    d_assessment.CheckD2(),
    d_assessment.CheckD3(),
    d_assessment.CheckD4(),
    d_assessment.CheckD5(),
    d_assessment.CheckD6(),
    d_assessment.CheckD7(),
    d_assessment.CheckD8(),
    d_assessment.CheckD9(),
    e_treatment_plan.CheckE1(),
    e_treatment_plan.CheckE2(),
    e_treatment_plan.CheckE3(),
    e_treatment_plan.CheckE4(),
    e_treatment_plan.CheckE5(),
    e_treatment_plan.CheckE6(),
    e_treatment_plan.CheckE7(),
    e_treatment_plan.CheckE8(),
    e_treatment_plan.CheckE9(),
    e_treatment_plan.CheckE10(),
    f_progress.CheckF1(),
    f_progress.CheckF2(),
    f_progress.CheckF3(),
    f_progress.CheckF4(),
    f_progress.CheckF5(),
    f_progress.CheckF6(),
    f_progress.CheckF7(),
    f_progress.CheckF8(),
    g_discharge_planning.CheckG1(),
    h_discharge_summary.CheckH1(),
    h_discharge_summary.CheckH2(),
    h_discharge_summary.CheckH3(),
    i_coordination.CheckI1(),
    i_coordination.CheckI2(),
    j_referrals.CheckJ1(),
    k_telehealth.CheckK1(),
    k_telehealth.CheckK2(),
]

_CHECK_MAP = {c.standard_id: c for c in ALL_CHECKS}


# ── Report dataclass ──────────────────────────────────────────────────────────

@dataclass
class NoteReport:
    note: Note
    results: list[CheckResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        actionable = [r for r in self.results if r.verdict in ("pass", "fail")]
        if not actionable:
            return 1.0
        return sum(1 for r in actionable if r.verdict == "pass") / len(actionable)

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.verdict == "fail"]

    @property
    def manual_reviews(self) -> list[CheckResult]:
        return [r for r in self.results if r.verdict == "manual_review"]


# ── Core runner ───────────────────────────────────────────────────────────────

def run_note(
    note: Note,
    judge: "Judge | None" = None,
    bundle: ContextBundle | None = None,
) -> NoteReport:
    """Run all applicable checks against a single note."""
    if judge is None:
        judge = NullJudge()

    results: list[CheckResult] = []
    applicable_ids = applicability.get_applicable_standards(note.note_type)

    for check in ALL_CHECKS:
        sid = check.standard_id
        if sid not in applicable_ids:
            continue
        try:
            result = check.run(note, judge, bundle)
        except Exception as exc:
            result = not_applicable(sid, f"Check error: {exc}")
        results.append(result)

    return NoteReport(note=note, results=results)


def _build_bundles(notes: list[Note]) -> dict[str, ContextBundle]:
    """Group notes by member name for cross-note checks."""
    bundles: dict[str, ContextBundle] = {}
    for note in notes:
        name = note.header.member_name or "unknown"
        if name not in bundles:
            bundles[name] = ContextBundle(member_name=name, notes=[])
        bundles[name].notes.append(note)
    return bundles


def run_batch(
    input_dir: Path,
    judge: "Judge | None" = None,
) -> list[NoteReport]:
    """Ingest all PDFs in input_dir and run compliance checks."""
    if judge is None:
        judge = NullJudge()

    notes = ingest_directory(input_dir)
    bundles = _build_bundles(notes)

    reports: list[NoteReport] = []
    for note in notes:
        bundle = bundles.get(note.header.member_name or "unknown")
        report = run_note(note, judge, bundle)
        reports.append(report)

    return reports
