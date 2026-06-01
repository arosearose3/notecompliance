# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`fixtnpdf` is a Python CLI tool that batch-corrects the clinician title in clinical progress note PDFs. It reads provider licensure dates from a CSV, compares each session's date against those thresholds, and writes corrected PDFs to an output directory without modifying the originals.

## Title logic

The CSV has two date columns per provider: `lpcc_date` (candidate licensure) and `lpc_date` (full licensure). Given a session date:

| Condition | Title written |
|---|---|
| session_date < lpcc_date | `Provider Name, Intern` |
| lpcc_date ≤ session_date < lpc_date | `Provider Name, LPCC` |
| session_date ≥ lpc_date | `Provider Name, LPC` |

## Data sources

- **Input PDFs**: directory of clinical progress note PDFs
- **CSV lookup** (`licensedates.csv`): columns `name`, `LPCC`, `LPC` — dates in `M/D/YYYY` format; provider name must match the `Clinician:` field in the PDF exactly
- **Output PDFs**: written to a separate output directory; input files are never overwritten

## PDF structure (confirmed from sample)

These are **plain-text PDFs** (not AcroForm), generated from HTML by an EHR system. Libraries: `pdfplumber` for reading, `pikepdf` for content-stream modification.

**Page layout (text-extraction order per page):**
```
[Note Type]                         ← e.g. "Consultation Note"
Boulder Emotional Wellness  Date and Time: 10/7/2025 1:00 PM ...
Clinician: Bridgid Lupetin, LPC     Duration: 56 minutes
Supervisor: Erica Johnson, LPC      Service Code: 90837
Patient: ...                        Location: ...
                                    Participants: ...
dummylink                           ← appears on every page; may overlap body text
[body content for this page]
[signature blocks — last page only]
Page X of Y                         ← always the final line
```

Key structural facts:
- The two-column header merges onto single lines in text extraction: `Clinician: Bridgid Lupetin, LPC Duration: 56 minutes`
- `Page 1 of N` at the end of a page's text marks the **first page of a new note** — the reliable note-boundary signal
- `dummylink` appears on every page but sometimes overlaps with body text characters (e.g., `D diuamgnmoysliisnk` = "Diagnosis" + "dummylink"); do not rely on it as a clean delimiter
- One PDF file contains multiple notes of different types (Consultation Note, Intake Note, Progress Note, and possibly others)

**Clinician field format:** `Clinician: Name, Title` — e.g. `Bridgid Lupetin, LPC`

**Session date location:** `Date and Time: MM/DD/YYYY HH:MM AM/PM - HH:MM AM/PM` in the page header

**Two locations to update per note** (both contain the credential):
1. Header line on every page: `Clinician: Bridgid Lupetin, LPC`
2. Signature block on the last page: `Bridgid Lupetin, LPC, Licensed Professional Counselor, License CO 22405, signed this note...`

## Intended CLI interface

```
python scanner.py [input_dir]        # diagnostic: report notes + titles (default: sourcedocs/)
python -m fixtnpdf --input <dir> --providers <csv> --output <dir>
```

## Running the scanner

```
python scanner.py                    # scans sourcedocs/, writes scan_results.csv
python scanner.py path/to/input/dir
```
