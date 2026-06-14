"""
Runner — orchestrates ingest → classify → checks → NoteReport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from compliance.ingest import ingest_directory, split_notes
from compliance.judges.null import NullJudge
from compliance.models import ContextBundle, Note
from compliance.checks.base import CheckResult, not_applicable
from compliance.ruleset import Ruleset, get_ruleset

if TYPE_CHECKING:
    from compliance.judges.base import Judge


# ── Report dataclass ──────────────────────────────────────────────────────────

@dataclass
class NoteReport:
    note: Note
    results: list[CheckResult] = field(default_factory=list)
    ruleset_id: str = "optum_commercial"

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
    ruleset: Ruleset | None = None,
) -> NoteReport:
    """Run all applicable checks against a single note."""
    if judge is None:
        judge = NullJudge()
    if ruleset is None:
        ruleset = get_ruleset()

    results: list[CheckResult] = []
    applicable_ids = set(ruleset.get_applicable_standards(note.note_type))

    for check in ruleset.checks():
        sid = check.standard_id
        if sid not in applicable_ids:
            continue
        try:
            result = check.run(note, judge, bundle)
        except Exception as exc:
            result = not_applicable(sid, f"Check error: {exc}")
        results.append(result)

    return NoteReport(note=note, results=results, ruleset_id=ruleset.id)


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
    ruleset: Ruleset | None = None,
) -> list[NoteReport]:
    """Ingest all PDFs in input_dir and run compliance checks."""
    if judge is None:
        judge = NullJudge()
    if ruleset is None:
        ruleset = get_ruleset()

    notes = ingest_directory(input_dir)
    bundles = _build_bundles(notes)

    reports: list[NoteReport] = []
    for note in notes:
        bundle = bundles.get(note.header.member_name or "unknown")
        report = run_note(note, judge, bundle, ruleset=ruleset)
        reports.append(report)

    return reports


# ── Back-compat: keep ALL_CHECKS accessible for code that imports it directly ──
# This is the single ALL_CHECKS; trainui/data.py re-exports from here.

def _get_default_checks():
    """Return the default ruleset's check list (lazy, avoids import cycles)."""
    return get_ruleset().checks()


# Provide a module-level ALL_CHECKS for backward compatibility
# (evaluated lazily on first access via __getattr__)
def __getattr__(name: str):
    if name == "ALL_CHECKS":
        return get_ruleset().checks()
    if name == "_CHECK_MAP":
        checks = get_ruleset().checks()
        return {c.standard_id: c for c in checks}
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
