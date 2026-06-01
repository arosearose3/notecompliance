#!/usr/bin/env python3
"""
scanner.py — inspect clinical progress note PDFs.

For each PDF in the input directory, reports:
  - filename and note count
  - per note: note type, session date, clinician name, existing title, license ID

Also writes scan_results.csv with the same data.

Usage:
    python scanner.py [input_dir]        (default: sourcedocs/)
"""

import csv
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required: pip install pdfplumber")

RE_CLINICIAN = re.compile(
    r"Clinician:\s+"
    r"([^,\n]+?)"                    # name — lazy, stops at comma or newline
    r"(?:,\s*(\S+))?"               # optional credential after comma
    r"(?=\s+(?:Duration:|Supervisor:|Service\s+Code:|Location:)|$|\n)",
    re.MULTILINE,
)
RE_DATE      = re.compile(r"Date and Time:\s+(\d{1,2}/\d{1,2}/\d{4})")
RE_NOTE_TYPE = re.compile(r"^((?:[A-Z][a-z]+ )*(?:Note|Plan|Summary))\s*$", re.MULTILINE)
RE_PAGE      = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)\s*$")


def _extract_credential_from_sig(text: str, clinician: str) -> str:
    """Return the credential immediately after the clinician's name in the signature block."""
    if not clinician:
        return ""
    m = re.compile(re.escape(clinician) + r",\s+(\S+)").search(text)
    return m.group(1).rstrip(",") if m else ""


def _extract_license_id(text: str, clinician: str) -> str:
    """
    Find the license ID in a signature block for the named clinician.
    Pattern: "Name, Cred, ..., License ST 12345"
    """
    if not clinician:
        return ""
    m = re.compile(
        re.escape(clinician)
        + r",\s+\S+,.*?License\s+[A-Z]{2}\s+(\d+)"
    ).search(text)
    return m.group(1) if m else ""


def scan_pdf(path: Path) -> list[dict]:
    """
    Return one dict per note.
    Header fields come from the first page (Page 1 of N).
    License ID comes from the last page (Page N of N) signature block.
    """
    notes: list[dict] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = RE_PAGE.search(text)
            if not m:
                continue

            page_num   = int(m.group(1))
            page_total = int(m.group(2))

            if page_num == 1:
                fields: dict = {}

                mc = RE_CLINICIAN.search(text)
                if mc:
                    fields["clinician"]      = mc.group(1).strip()
                    fields["existing_title"] = (mc.group(2) or "").strip()

                md = RE_DATE.search(text)
                if md:
                    fields["session_date"] = md.group(1)

                mt = RE_NOTE_TYPE.search(text)
                if mt:
                    fields["note_type"] = mt.group(1).strip()

                notes.append(fields)

            # Last page carries the signature block: extract license ID and,
            # when the header had no credential, fill it in from the signature.
            # For single-page notes page_num == page_total == 1, so this runs
            # on the same pass as the block above.
            if page_num == page_total and notes:
                clinician = notes[-1].get("clinician", "")
                notes[-1]["license_id"] = _extract_license_id(text, clinician)
                if not notes[-1].get("existing_title"):
                    notes[-1]["existing_title"] = _extract_credential_from_sig(text, clinician)

    return notes


def main():
    input_dir  = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sourcedocs")
    output_csv = Path("scan_results.csv")

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {input_dir}")
        sys.exit(1)

    rows = []
    for pdf_path in pdf_files:
        notes = scan_pdf(pdf_path)
        print(f"\n{pdf_path.name}  —  {len(notes)} note(s)")
        print(
            f"  {'Note Type':<22}  {'Session Date':<14}  "
            f"{'Clinician':<28}  {'Title':<8}  License ID"
        )
        print(f"  {'-'*22}  {'-'*14}  {'-'*28}  {'-'*8}  {'-'*10}")
        for n in notes:
            print(
                f"  {n.get('note_type', '?'):<22}  "
                f"{n.get('session_date', '?'):<14}  "
                f"{n.get('clinician', '?'):<28}  "
                f"{n.get('existing_title', '?'):<8}  "
                f"{n.get('license_id', '')}"
            )
            rows.append({
                "filename":       pdf_path.name,
                "note_type":      n.get("note_type", ""),
                "session_date":   n.get("session_date", ""),
                "clinician":      n.get("clinician", ""),
                "existing_title": n.get("existing_title", ""),
                "license_id":     n.get("license_id", ""),
            })

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "filename", "note_type", "session_date",
                "clinician", "existing_title", "license_id",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nResults written to {output_csv}")


if __name__ == "__main__":
    main()
