"""
Generate per-note HTML reports with highlighted findings.

One HTML file per note, plus an index.html listing all notes.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compliance.runner import NoteReport

_VERDICT_COLORS = {
    "pass":           "#2d7a2d",
    "fail":           "#c0392b",
    "manual_review":  "#e67e22",
    "not_applicable": "#7f8c8d",
}

_VERDICT_LABELS = {
    "pass":           "PASS",
    "fail":           "FAIL",
    "manual_review":  "MANUAL REVIEW",
    "not_applicable": "N/A",
}

_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem; color: #222; }
h1 { font-size: 1.4rem; border-bottom: 2px solid #ccc; padding-bottom: .5rem; }
h2 { font-size: 1.1rem; margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th { background: #f0f0f0; text-align: left; padding: .4rem .6rem; border: 1px solid #ccc; }
td { padding: .35rem .6rem; border: 1px solid #ddd; vertical-align: top; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
         color: #fff; font-weight: bold; font-size: .8rem; }
.excerpt { background: #fffbea; border-left: 3px solid #e6c800;
           padding: .3rem .5rem; margin: .2rem 0; font-size: .85rem;
           font-family: monospace; white-space: pre-wrap; }
.summary { display: flex; gap: 2rem; flex-wrap: wrap; margin: 1rem 0; }
.stat { background: #f9f9f9; border: 1px solid #ddd; border-radius: 6px;
        padding: .5rem 1rem; min-width: 8rem; text-align: center; }
.stat-val { font-size: 1.8rem; font-weight: bold; }
"""


def _badge(verdict: str) -> str:
    color = _VERDICT_COLORS.get(verdict, "#999")
    label = _VERDICT_LABELS.get(verdict, verdict.upper())
    return f'<span class="badge" style="background:{color}">{label}</span>'


def _note_html(report: "NoteReport") -> str:
    note = report.note
    h = note.header

    # Summary counts
    counts = {v: 0 for v in _VERDICT_COLORS}
    for r in report.results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    member = html.escape(h.member_name or "Unknown")
    clinician = html.escape(h.clinician or "Unknown")
    svc_date = str(h.service_date) if h.service_date else "—"
    doc_type = note.note_type.replace("_", " ").title()
    source = html.escape(note.source_pdf.name)

    rows = []
    for result in report.results:
        if result.verdict == "not_applicable":
            continue
        exc_html = "".join(
            f'<div class="excerpt">{html.escape(e)}</div>'
            for e in result.excerpts
        )
        judge_note = f" <em>({result.judge_used})</em>" if result.judge_used else ""
        rows.append(
            f"<tr>"
            f"<td><strong>{result.standard_id}</strong></td>"
            f"<td>{_badge(result.verdict)}{judge_note}</td>"
            f"<td>{html.escape(result.rationale)}{exc_html}</td>"
            f"</tr>"
        )

    table = (
        "<table><thead><tr>"
        "<th>Standard</th><th>Verdict</th><th>Rationale / Evidence</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    ) if rows else "<p><em>No actionable findings (all N/A).</em></p>"

    pass_pct = f"{report.pass_rate * 100:.0f}%"

    stats = "".join(
        f'<div class="stat"><div class="stat-val" style="color:{_VERDICT_COLORS[v]}">'
        f'{counts[v]}</div><div>{_VERDICT_LABELS[v]}</div></div>'
        for v in ["fail", "manual_review", "pass"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<title>Compliance Report — {member}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Compliance Report</h1>
<p><strong>Source:</strong> {source} &nbsp;|&nbsp;
   <strong>Type:</strong> {doc_type} &nbsp;|&nbsp;
   <strong>Member:</strong> {member} &nbsp;|&nbsp;
   <strong>Clinician:</strong> {clinician} &nbsp;|&nbsp;
   <strong>Date:</strong> {svc_date} &nbsp;|&nbsp;
   <strong>Pass rate:</strong> {pass_pct}</p>
<div class="summary">{stats}</div>
<h2>Findings (N/A rows hidden)</h2>
{table}
</body></html>"""


def _index_html(reports: list["NoteReport"], note_files: list[str]) -> str:
    rows = []
    for report, fname in zip(reports, note_files):
        note = report.note
        h = note.header
        fail_count = len(report.failures)
        mr_count = len(report.manual_reviews)
        verdict_color = "#c0392b" if fail_count > 0 else ("#e67e22" if mr_count > 0 else "#2d7a2d")
        rows.append(
            f"<tr>"
            f"<td><a href='{fname}'>{html.escape(note.source_pdf.name)}</a></td>"
            f"<td>{note.note_type}</td>"
            f"<td>{html.escape(h.member_name or '—')}</td>"
            f"<td>{h.service_date or '—'}</td>"
            f"<td style='color:{verdict_color};font-weight:bold'>{fail_count}</td>"
            f"<td>{mr_count}</td>"
            f"<td>{report.pass_rate * 100:.0f}%</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<title>Compliance Audit Index</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Compliance Audit — Note Index</h1>
<table>
<thead><tr>
<th>File</th><th>Type</th><th>Member</th><th>Date</th>
<th>Failures</th><th>Manual Review</th><th>Pass Rate</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
</body></html>"""


def write_html(reports: list["NoteReport"], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    note_files = []

    for i, report in enumerate(reports):
        note = report.note
        member_slug = (note.header.member_name or "unknown").replace(" ", "_").lower()
        date_slug = str(note.header.service_date or "nodate").replace("-", "")
        fname = f"note_{i:04d}_{date_slug}_{member_slug}_{note.note_type}.html"
        note_files.append(fname)
        (output_dir / fname).write_text(_note_html(report), encoding="utf-8")

    (output_dir / "index.html").write_text(
        _index_html(reports, note_files), encoding="utf-8"
    )
