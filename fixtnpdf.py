#!/usr/bin/env python3
"""
fixtnpdf.py - Correct clinician titles in clinical progress note PDFs.

For each PDF in the input directory:
  - Reads the Clinician field and session date from each note header
  - Looks up the provider in the licensure CSV
    (columns: name, LPCC, LPCC ID, LPC, LPC ID)
  - Computes the correct credential: Intern / LPCC / LPC
  - Replaces both the credential label and the license ID in:
      · the header line (every page of the note)
      · the signature block (last page of the note)
  - Writes corrected PDF to the output directory; originals are untouched

Usage:
    python fixtnpdf.py --input <dir> --providers <csv> --output <dir>
"""

import argparse
import csv
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    import fitz          # PyMuPDF
    import pdfplumber
except ImportError as e:
    sys.exit(f"Missing dependency: {e}\n  pip install pymupdf pdfplumber")

from compliance.rewrite.types import RewritePlan, TargetSpan
from compliance.rewrite.applier import apply_plan


# ---------------------------------------------------------------------------
# Providers and supervisors CSVs
# ---------------------------------------------------------------------------

def load_tracker(csv_path: Path) -> dict:
    """
    Returns {(last_lower, first_lower): set_of_dates}.
    No header row: col C (index 2) = last name, col D (index 3) = first name,
    col H (index 7) = session date.
    """
    tracker: dict = {}
    with open(csv_path, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            last  = row[2].strip().lower()
            first = row[3].strip().lower()
            d     = _parse_date(row[7].strip())
            if last and first and d:
                tracker.setdefault((last, first), set()).add(d)
    return tracker


def load_supervisors(csv_path: Path) -> dict:
    """Returns {name: lpc_id}."""
    supervisors = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            name = row["name"].strip()
            supervisors[name] = row["LPC ID"].strip()
    return supervisors


def load_providers(csv_path: Path) -> dict:
    """Returns {name: {lpcc, lpcc_id, lpc, lpc_id}}."""
    providers = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            name = row["name"].strip()
            providers[name] = {
                "lpcc":    _parse_date(row.get("LPCC")),
                "lpcc_id": (row.get("LPCC ID") or "").strip(),
                "lpc":     _parse_date(row.get("LPC")),
                "lpc_id":  (row.get("LPC ID") or "").strip(),
            }
    return providers


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {s!r}")


# ---------------------------------------------------------------------------
# Credential logic
# ---------------------------------------------------------------------------

def compute_credential(session_date, provider: dict) -> tuple[str, str | None]:
    """
    Returns (title, license_id).
    license_id is None for Intern (no license applies).
    Missing dates (None) mean the threshold has not been reached.
    """
    if provider["lpc"] and session_date >= provider["lpc"]:
        return "LPC", provider["lpc_id"]
    elif provider["lpcc"] and session_date >= provider["lpcc"]:
        return "LPCC", provider["lpcc_id"]
    else:
        return "Intern", None


# ---------------------------------------------------------------------------
# Page scanning with pdfplumber
# ---------------------------------------------------------------------------

RE_PATIENT   = re.compile(r"Patient:\s+([^\n]+)")
RE_CLINICIAN = re.compile(
    r"Clinician:\s+"
    r"([^,\n]+?)"                    # name — lazy, stops at comma or newline
    r"(?:,\s*(\S+))?"               # optional credential after comma
    r"(?=\s+(?:Duration:|Supervisor:|Service\s+Code:|Location:)|$|\n)",
    re.MULTILINE,
)
RE_DATE      = re.compile(r"Date and Time:\s+(\d{1,2}/\d{1,2}/\d{4})")
RE_PAGE      = re.compile(r"Page\s+(\d+)\s+of\s+\d+\s*$")


def _extract_credential_from_sig(text: str, clinician: str) -> str:
    """Return the credential immediately after the clinician's name in the signature block."""
    if not clinician:
        return ""
    m = re.compile(re.escape(clinician) + r",\s+(\S+)").search(text)
    return m.group(1).rstrip(",") if m else ""


def scan_pages(pdf_path: Path) -> list[dict]:
    """Return one dict per PDF page with extracted header fields."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            info: dict = {"idx": i}

            m = RE_CLINICIAN.search(text)
            if m:
                info["clinician"]     = m.group(1).strip()
                info["current_title"] = (m.group(2) or "").strip()
                # current_title reflects only what is in the header.
                # Empty string means no credential in the header → insert needed.

            m = RE_DATE.search(text)
            if m:
                info["session_date"] = _parse_date(m.group(1))

            m = RE_PATIENT.search(text)
            if m:
                raw = m.group(1).strip()
                for stopper in ("DOB ", "DOB:", "Location:", "Service Code:", "Participants:"):
                    if stopper in raw:
                        raw = raw.split(stopper)[0]
                info["member_name"] = raw.strip().rstrip(",; \t")

            m = RE_PAGE.search(text)
            if m:
                info["page_num"] = int(m.group(1))

            pages.append(info)
    return pages


def build_corrections(pages: list[dict], providers: dict) -> dict:
    """
    Returns {page_idx: (clinician, old_title, new_title, new_id)}.
    Only includes pages where a credential change is needed.
    A note's correction is determined from its first page (page_num == 1)
    and propagated to all subsequent pages of the same note.
    """
    corrections: dict = {}
    current: tuple | None = None

    for page in pages:
        if page.get("page_num") == 1:
            clinician    = page.get("clinician")
            old_title    = page.get("current_title")
            session_date = page.get("session_date")

            if clinician and session_date:
                if clinician in providers:
                    new_title, new_id = compute_credential(session_date, providers[clinician])
                    if new_title != old_title:
                        current = (clinician, old_title, new_title, new_id)
                    else:
                        current = None
                else:
                    print(f"  WARNING: '{clinician}' not found in providers CSV", file=sys.stderr)
                    current = None
            else:
                current = None

        if current is not None:
            corrections[page["idx"]] = current

    return corrections


def build_note_groups(pages: list[dict]) -> list[dict]:
    """
    Group pages into per-note dicts.  Each dict has:
      page_indices  – list of source-PDF page indices
      clinician, current_title, session_date, member_name  – from page_num==1
    """
    groups: list[dict] = []
    current: dict | None = None
    for page in pages:
        if page.get("page_num") == 1:
            current = {
                "page_indices":  [page["idx"]],
                "clinician":     page.get("clinician"),
                "current_title": page.get("current_title", ""),
                "session_date":  page.get("session_date"),
                "member_name":   page.get("member_name"),
            }
            groups.append(current)
        elif current is not None:
            current["page_indices"].append(page["idx"])
    return groups


def _note_matches_tracker(group: dict, tracker: dict) -> bool:
    member  = group.get("member_name") or ""
    session = group.get("session_date")
    if not member or not session:
        return False
    parts = member.split()
    if len(parts) < 2:
        return False
    first = parts[0].lower()
    last  = parts[-1].lower()
    return session in tracker.get((last, first), set())


def build_corrections_for_groups(note_groups: list[dict], providers: dict) -> dict:
    """
    Returns {page_idx: (clinician, old_title, new_title, new_id)}
    for every page in the supplied note groups that needs a credential change.
    """
    corrections: dict = {}
    for group in note_groups:
        clinician    = group.get("clinician")
        old_title    = group.get("current_title", "")
        session_date = group.get("session_date")

        if not clinician or not session_date:
            continue
        if clinician not in providers:
            print(f"  WARNING: '{clinician}' not found in providers CSV", file=sys.stderr)
            continue

        new_title, new_id = compute_credential(session_date, providers[clinician])
        if new_title == old_title:
            continue

        correction = (clinician, old_title, new_title, new_id)
        for idx in group["page_indices"]:
            corrections[idx] = correction
    return corrections


# ---------------------------------------------------------------------------
# PDF modification — delegates to compliance.rewrite shared engine
# ---------------------------------------------------------------------------

from compliance.rewrite.actions.provider_title import (
    _locate_affected, _locate_insert, _substitute_span_text,
    compute_credential as _compute_credential,
)
from compliance.rewrite.actions.supervisor_credential import _fix_supervisor_text


def apply_corrections(
    pdf_path: Path,
    corrections: dict,
    output_path: Path,
    supervisors: dict | None = None,
    pages_to_include: set | None = None,
) -> int:
    """
    Build an output PDF containing only pages_to_include (all pages if None),
    apply clinician credential corrections and supervisor fixes, and save.
    Returns the number of pages written (pages that had at least one span changed).

    Delegates redact/reinsert to compliance.rewrite.apply_plan so all PDF
    modification is in one audited place.
    """
    supervisors = supervisors or {}

    src = fitz.open(str(pdf_path))
    if pages_to_include is None:
        pages_to_include = set(range(len(src)))
    src.close()

    plan = RewritePlan()

    src = fitz.open(str(pdf_path))
    pages_with_changes: set[int] = set()

    for src_idx in sorted(pages_to_include):
        page = src[src_idx]

        if src_idx in corrections:
            clinician, old_title, new_title, new_id = corrections[src_idx]
            if old_title:
                located = _locate_affected(page, f"{clinician}, {old_title}", f"{clinician}, {new_title}", new_id)
                for span in located:
                    new_text = _substitute_span_text(span.old_text, f"{clinician}, {old_title}", f"{clinician}, {new_title}", new_id)
                    plan.add(span, new_text)
                    pages_with_changes.add(src_idx)
            else:
                from compliance.rewrite.actions.provider_title import _locate_insert as _li
                located = _li(page, clinician, new_title, new_id)
                for span in located:
                    text = span.old_text
                    stripped = text.strip()
                    if stripped == clinician:
                        new_text = text.replace(
                            clinician,
                            f"{clinician}, {new_title}, #{new_id}" if new_id else f"{clinician}, {new_title}",
                            1,
                        )
                    else:
                        import re as _re
                        _RE_SIG_CRED = _re.compile(r",\s+(\S+)")
                        after = text[text.index(clinician + ",") + len(clinician):]
                        m = _RE_SIG_CRED.match(after)
                        existing_cred = m.group(1).rstrip(",") if m else old_title
                        new_text = _substitute_span_text(text, f"{clinician}, {existing_cred}", f"{clinician}, {new_title}", new_id)
                    plan.add(span, new_text)
                    pages_with_changes.add(src_idx)

        for sup_name, lpc_id in supervisors.items():
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        new_text = _fix_supervisor_text(span["text"], sup_name, lpc_id)
                        if new_text is not None:
                            from compliance.rewrite.types import TargetSpan as _TS
                            plan.add(
                                _TS(
                                    page_index=src_idx,
                                    rect=tuple(span["bbox"]),
                                    origin=tuple(span["origin"]),
                                    size=span["size"],
                                    font=span.get("font", "helv"),
                                    old_text=span["text"],
                                ),
                                new_text,
                            )
                            pages_with_changes.add(src_idx)

    src.close()

    if not plan.entries:
        # Nothing to change — write a copy of the selected pages unchanged
        src2 = fitz.open(str(pdf_path))
        out = fitz.open()
        for src_idx in sorted(pages_to_include):
            out.insert_pdf(src2, from_page=src_idx, to_page=src_idx)
        src2.close()
        out.save(str(output_path))
        out.close()
        return 0

    apply_plan(
        source_pdf=pdf_path,
        output_pdf=output_path,
        plan=plan,
        pages_to_include=pages_to_include,
        action_id="provider_title+supervisor_credential",
    )
    return len(pages_with_changes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix clinician credentials in progress note PDFs"
    )
    parser.add_argument("--input",       required=True, help="Directory of input PDFs")
    parser.add_argument("--providers",   required=True, help="Provider licensure CSV")
    parser.add_argument("--output",      required=True, help="Output directory")
    parser.add_argument("--supervisors", default=None,  help="Supervisors CSV (name, LPC ID)")
    parser.add_argument("--tracker",     default=None,
                        help="Title-tracker CSV; limits output to listed member+date pairs")
    args = parser.parse_args()

    input_dir  = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    providers = load_providers(Path(args.providers))
    print(f"Loaded {len(providers)} provider(s) from {args.providers}")

    supervisors: dict = {}
    if args.supervisors:
        supervisors = load_supervisors(Path(args.supervisors))
        print(f"Loaded {len(supervisors)} supervisor(s) from {args.supervisors}")

    tracker: dict = {}
    if args.tracker:
        tracker = load_tracker(Path(args.tracker))
        print(f"Loaded tracker: {sum(len(v) for v in tracker.values())} session(s) "
              f"across {len(tracker)} member(s) from {args.tracker}")

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {input_dir}")
        sys.exit(1)

    total_pages = 0
    files_written = 0
    for pdf_path in pdf_files:
        pages       = scan_pages(pdf_path)
        note_groups = build_note_groups(pages)

        # Filter to tracker-matched notes when tracker is active.
        if tracker:
            matched = [g for g in note_groups if _note_matches_tracker(g, tracker)]
        else:
            matched = note_groups

        if not matched and not supervisors:
            continue  # nothing to do for this file — no output

        # If tracker is active and nothing matched, skip entirely.
        if tracker and not matched:
            continue

        print(f"\n{pdf_path.name}")

        corrections    = build_corrections_for_groups(matched, providers)
        pages_to_include = set()
        for g in matched:
            pages_to_include.update(g["page_indices"])

        if corrections:
            summary: dict = {}
            for correction in corrections.values():
                summary[correction] = summary.get(correction, 0) + 1
            for (clinician, old, new, new_id), pg_count in summary.items():
                id_note = f"  license ID → {new_id}" if new_id else ""
                print(f"  {clinician}: {old} → {new}{id_note}  ({pg_count} page(s))")

        if supervisors:
            for name, lpc_id in supervisors.items():
                print(f"  Supervisor {name}: LPC, #{lpc_id}")

        output_path   = output_dir / pdf_path.name
        pages_modified = apply_corrections(
            pdf_path, corrections, output_path, supervisors, pages_to_include
        )
        total_pages  += pages_modified
        files_written += 1
        notes_label   = f"{len(matched)} note(s), {len(pages_to_include)} page(s)"
        print(f"  → {output_path.name}  [{notes_label}]")

    print(f"\nDone. {files_written} file(s) written, {total_pages} page(s) modified.")


if __name__ == "__main__":
    main()
