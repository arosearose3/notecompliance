# fixtnpdf User Guide

`fixtnpdf.py` reads clinical progress note PDFs, corrects clinician and
supervisor credentials, and writes fixed PDFs to an output directory.
Originals are never modified.

---

## Quick start

```bash
python fixtnpdf.py \
  --input    sourcedocs/ \
  --providers licensedates.csv \
  --supervisors supervisors.csv \
  --tracker  titletracker.csv \
  --output   output/
```

---

## Command-line arguments

| Argument | Required | Description |
|---|---|---|
| `--input` | Yes | Directory containing the source PDF files to process |
| `--providers` | Yes | CSV of rendering clinician licensure dates and IDs |
| `--output` | Yes | Directory where corrected PDFs are written (created if absent) |
| `--supervisors` | No | CSV of supervising clinician names and LPC license IDs |
| `--tracker` | No | Optum title-tracker export; limits output to specific member/date pairs |

### `--input`

A folder of PDF files exported from the EHR. Each file may contain one or
more clinical notes of any type (Progress Note, Treatment Plan, Intake,
Consultation, etc.). The tool detects note boundaries automatically using the
`Page X of Y` stamp in each note's header.

### `--providers`

Points to `licensedates.csv` (see below). The tool reads this file first; if
a clinician name found in a PDF is not listed here, a warning is printed and
that note is left unchanged.

### `--output`

The corrected PDFs are written here with the same filename as the source.
When `--tracker` is active, only matched notes are included in each output
file; a source PDF with no matching notes produces no output file.

### `--supervisors`

Points to `supervisors.csv` (see below). When supplied, every page of every
output PDF is scanned for supervisor names and their credential line is
updated. This argument is optional; omit it to skip supervisor corrections.

### `--tracker`

Points to `titletracker.csv` (see below). When supplied:

- Only notes whose member name **and** session date appear in the tracker
  are included in the output.
- A source PDF that has no matching notes produces **no output file**.
- A source PDF that has some matching notes produces an output file
  containing **only those note pages** — unmatched notes are excluded.

Omit `--tracker` to process every note in every source PDF.

---

## Collateral files

### `licensedates.csv` — provider licensure dates

**Purpose:** tells the tool what credential each rendering clinician should
carry on a given session date, and what their license number is.

**Format:** CSV with a header row.

| Column | Description | Example |
|---|---|---|
| `name` | Clinician's full name — must match the `Clinician:` field in the PDF exactly (case-sensitive) | `Rachel Kelley` |
| `LPCC` | Date the clinician received their LPCC (candidate) license | `6/4/2025` |
| `LPCC ID` | LPCC license number | `23486` |
| `LPC` | Date the clinician received their full LPC license | `6/23/2025` |
| `LPC ID` | LPC license number | `22405` |

**Credential logic applied per session date:**

| Condition | Credential written |
|---|---|
| Session date ≥ LPC date | `LPC, #<LPC ID>` |
| Session date ≥ LPCC date (but < LPC date) | `LPCC, #<LPCC ID>` |
| Session date < LPCC date, or all dates blank | `Intern` (no license number) |

**Notes:**

- Dates accept `M/D/YYYY` or `M/D/YY` format (e.g. `6/2/21` is treated as
  2021).
- Leave `LPC` and `LPC ID` blank for clinicians who have not yet reached
  full licensure.
- Leave both `LPCC` and `LPC` blank for clinicians who have no licensure
  at all (Intern).
- A name with no dates at all (like `Brittney McIngvale,,,,`) is treated as
  Intern.
- If a clinician name in a PDF is not found in this file, the tool prints a
  warning and leaves that note unchanged.

**Example:**

```
name,LPCC,LPCC ID,LPC,LPC ID
Bridgid Lupetin,2/14/2023,20471,6/23/2025,22405
Rachel Kelley,6/4/2025,23486,,
Brittney McIngvale,,,,
Niccole Fortunato,6/2/21,18522,6/12/24,20828
```

---

### `supervisors.csv` — supervising clinician license IDs

**Purpose:** ensures every appearance of a supervisor's name in the PDFs
carries their LPC credential and license number.

**Format:** CSV with a header row.

| Column | Description | Example |
|---|---|---|
| `name` | Supervisor's full name as it appears in the PDF | `Erica Johnson` |
| `LPC ID` | LPC license number | `14267` |

**What the tool does:** for every page in every output PDF, it finds any
span containing a supervisor name and rewrites it to:

- `Supervisor: Erica Johnson, LPC, #14267` (in the page header)
- `Erica Johnson, LPC, #14267, signed this note...` (in the signature block)

Any degree title text between the license number and "signed this note"
(e.g. "Licensed Professional Counselor") is stripped so the line reads
cleanly.

**Example:**

```
name,LPC ID
Andrew Rose,11337
Elizabeth Driscoll,16044
Erica Johnson,14267
```

---

### `titletracker.csv` — Optum title-tracker export

**Purpose:** a denial/audit export from Optum that identifies which specific
member sessions need corrected documentation. When passed with `--tracker`,
the tool outputs **only** the notes that appear in this list.

**Format:** CSV with **no header row**. The tool reads these columns by
position:

| Column | Index | Description | Example |
|---|---|---|---|
| C | 2 | Member last name (uppercase) | `BURBULES` |
| D | 3 | Member first name (uppercase) | `THESSA` |
| H | 7 | Session date (`M/D/YYYY`) | `10/7/2024` |

All other columns (reviewer, claim number, denial reason, etc.) are ignored.

**Matching logic:** a note is included in output when:
1. The note's `Patient:` field matches the tracker's first + last name
   (case-insensitive), **and**
2. The note's session date (`Date and Time:`) matches the tracker's session
   date exactly.

Multiple rows for the same member accumulate into a set of dates. A note
must match on **both** name and date to be included.

**What "output" means with `--tracker`:**

- If a source PDF contains 10 notes and 3 match the tracker, the output
  PDF contains only those 3 notes (their pages only).
- If a source PDF contains no matching notes, no output file is written
  for it.

---

## What the tool writes

For each page in each matched note, the tool:

1. **Clinician header** (every page) — updates `Clinician: Name` to
   `Clinician: Name, Credential, #LicenseID`.
2. **Clinician signature block** (last page of note) — updates
   `Name, OldCredential, signed this note...` to
   `Name, NewCredential, #LicenseID, signed this note...`, stripping any
   retained degree title in between.
3. **Supervisor header** (every page, when `--supervisors` provided) —
   updates `Supervisor: Name` to `Supervisor: Name, LPC, #LicenseID`.
4. **Supervisor signature block** — same cleanup as clinician.

The license number is written as `#NNNNN` (hash + digits) rather than
`License CO NNNNN` to fit within the line width of the original layout.

---

## Diagnostic tool: `scanner.py`

Before running the fixer, use the scanner to inspect what the tool will see:

```bash
python scanner.py                    # scans sourcedocs/, writes scan_results.csv
python scanner.py path/to/input/dir  # scan a different directory
```

Output columns: filename, note type, session date, clinician name, existing
title, license ID. Useful for verifying name spelling before adding entries
to `licensedates.csv`.

---

## Troubleshooting

**"WARNING: 'Name' not found in providers CSV"**
The clinician name in the PDF does not match any row in `licensedates.csv`.
Check spelling and capitalisation with `scanner.py`, then add or correct the
entry in the CSV.

**A note is not in the output**
If `--tracker` is active, the note's member name or session date may not
match any tracker row. Run `scanner.py` to confirm the member name and date
as extracted, and compare against the tracker CSV.

**Two different spellings of the same name in `licensedates.csv`**
The CSV is matched case-sensitively against the PDF text. Both spellings
should be listed as separate rows with the same dates and IDs until the
source PDFs are consistent.

**Output signature line looks cramped**
The tool rewrites text at the original font size. If the corrected line is
visually long (e.g. LPCC + license number added to an Intern signature), the
text is still correct; only the visual density changes.
