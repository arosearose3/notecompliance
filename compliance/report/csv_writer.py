"""Write findings as a CSV (one row per finding)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compliance.runner import NoteReport

FIELDNAMES = [
    "source_pdf", "note_type", "member", "service_date", "clinician",
    "standard_id", "verdict", "rationale", "excerpts", "judge_used",
]


def write_csv(
    reports: list["NoteReport"],
    output_path: Path,
    *,
    only_failures: bool = True,
) -> None:
    """
    Write findings to CSV.  By default includes only fail and manual_review
    rows; pass only_failures=False to include all verdicts.
    """
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for report in reports:
            note = report.note
            for result in report.results:
                if only_failures and result.verdict in ("pass", "not_applicable"):
                    continue
                writer.writerow({
                    "source_pdf":  note.source_pdf.name,
                    "note_type":   note.note_type,
                    "member":      note.header.member_name or "",
                    "service_date": str(note.header.service_date) if note.header.service_date else "",
                    "clinician":   note.header.clinician or "",
                    "standard_id": result.standard_id,
                    "verdict":     result.verdict,
                    "rationale":   result.rationale,
                    "excerpts":    " | ".join(result.excerpts),
                    "judge_used":  result.judge_used or "",
                })
