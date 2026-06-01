"""Write findings as newline-delimited JSON (findings.jsonl)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compliance.runner import NoteReport


def write_jsonl(reports: list["NoteReport"], output_path: Path) -> None:
    with open(output_path, "w") as f:
        for report in reports:
            note = report.note
            for result in report.results:
                record = {
                    "source_pdf":    str(note.source_pdf.name),
                    "note_type":     note.note_type,
                    "member":        note.header.member_name,
                    "service_date":  str(note.header.service_date) if note.header.service_date else None,
                    "clinician":     note.header.clinician,
                    "standard_id":   result.standard_id,
                    "verdict":       result.verdict,
                    "rationale":     result.rationale,
                    "excerpts":      list(result.excerpts),
                    "page_numbers":  list(result.page_numbers),
                    "judge_used":    result.judge_used,
                }
                f.write(json.dumps(record) + "\n")
