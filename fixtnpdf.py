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
# PDF modification with pymupdf
# ---------------------------------------------------------------------------

RE_LICENSE         = re.compile(r"License ([A-Z]{2}) (\d+)")
RE_LICENSE_NOSTATE = re.compile(r"License (\d+)")
RE_SIGNED          = re.compile(r",?\s*signed\s+this\s+note", re.IGNORECASE)


def _clean_signature_span(text: str, name: str, credential: str,
                           lpc_id: str | None) -> str:
    """
    Reconstruct a signature span as: name, credential[, #lpc_id], signed this note...

    Strips ALL intermediate text between the name and "signed this note" — whether
    it sits between the credential and the license, or between the license and the
    signed phrase.  No-ops when 'signed this note' is absent or name is missing.
    """
    if "signed this note" not in text.lower() or name not in text:
        return text

    prefix = text[: text.index(name)]           # text before the name (usually empty)
    signed_m = RE_SIGNED.search(text)
    if not signed_m:
        return text

    suffix = text[signed_m.end():]              # text after "signed this note"
    cred_part = f"{credential}, #{lpc_id}" if lpc_id else credential
    return f"{prefix}{name}, {cred_part}, signed this note{suffix}"


def _substitute_span_text(span_text: str, old_cred_text: str, new_cred_text: str,
                           new_id: str | None) -> str:
    """
    Replace the credential label and, for signature spans, also the license ID.
    License is written as '#NNNNN' (no 'License CO' prefix) to save line width.
    If a 'License XX NNNNN' token already exists it is replaced; if the span had
    no license token (e.g. an Intern signature), '#NNNNN' is inserted after the
    credential.
    """
    result = span_text.replace(old_cred_text, new_cred_text)
    if new_id is not None:
        m = RE_LICENSE.search(result)
        if m:
            result = result.replace(
                f"License {m.group(1)} {m.group(2)}",
                f"#{new_id}",
            )
        elif new_cred_text in result:
            result = result.replace(
                new_cred_text,
                f"{new_cred_text}, #{new_id}",
                1,
            )
    # For signature spans: reconstruct the line from scratch so that ALL
    # intermediate degree/title text is removed regardless of its position.
    if "signed this note" in result.lower():
        parts = new_cred_text.split(", ", 1)   # "Name, Credential"
        if len(parts) == 2:
            result = _clean_signature_span(result, parts[0], parts[1], new_id)
    return result


def _find_affected_spans(page: fitz.Page, old_cred_text: str, new_cred_text: str,
                         new_id: str | None) -> list[dict]:
    """Find all spans containing old_cred_text and build their replacement info."""
    results = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if old_cred_text in span["text"]:
                    results.append({
                        "rect":     fitz.Rect(span["bbox"]),
                        "origin":   fitz.Point(span["origin"]),
                        "new_text": _substitute_span_text(
                            span["text"], old_cred_text, new_cred_text, new_id
                        ),
                        "size":     span["size"],
                    })
    return results


RE_SIG_CRED = re.compile(r",\s+(\S+)")   # first token after comma in signature


def _find_insert_spans(page: fitz.Page, clinician: str, new_title: str,
                       new_id: str | None) -> list[dict]:
    """
    For notes where the credential was absent from the header.

    In some EHR templates fitz splits the header into separate spans:
      'Clinician:'  and  'Rachel Kelley'  (not a single combined span).

    Two strategies per span:
      1. Header span — text is exactly the clinician name (no comma/credential):
         replace the name with "name, new_title".
      2. Signature span — name followed by comma + existing credential:
         only replace if the existing credential differs from new_title.
    """
    results = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"]
                stripped = text.strip()

                # Strategy 1: standalone name span (header, no credential present)
                if stripped == clinician:
                    results.append({
                        "rect":     fitz.Rect(span["bbox"]),
                        "origin":   fitz.Point(span["origin"]),
                        "new_text": text.replace(
                            clinician,
                            f"{clinician}, {new_title}, #{new_id}" if new_id else f"{clinician}, {new_title}",
                            1,
                        ),
                        "size":     span["size"],
                    })
                    continue

                # Strategy 2: signature span — name + comma + existing credential
                if clinician + "," in text:
                    after = text[text.index(clinician + ",") + len(clinician):]
                    m = RE_SIG_CRED.match(after)
                    if m:
                        existing_cred = m.group(1).rstrip(",")
                        if existing_cred != new_title:
                            old_sig = f"{clinician}, {existing_cred}"
                            new_sig = f"{clinician}, {new_title}"
                            new_text = _substitute_span_text(text, old_sig, new_sig, new_id)
                            results.append({
                                "rect":     fitz.Rect(span["bbox"]),
                                "origin":   fitz.Point(span["origin"]),
                                "new_text": new_text,
                                "size":     span["size"],
                                "font":     span.get("font", "helv"),
                            })

    return results


def _fix_supervisor_span(text: str, name: str, lpc_id: str) -> str | None:
    """
    Return corrected span text for a span containing a supervisor name,
    or None if no change is needed.

    Target format: "Name, LPC, #ID" (header) or
    "Name, LPC, [Degree], #ID, signed..." (signature).
    """
    if name not in text:
        return None

    result = text
    id_tag = f"#{lpc_id}"

    # Normalise any existing "License CO NNNNN" or "License NNNNN" to "#ID".
    m = RE_LICENSE.search(result)
    if m:
        result = result.replace(f"License {m.group(1)} {m.group(2)}", id_tag)
    else:
        m = RE_LICENSE_NOSTATE.search(result)
        if m:
            result = result.replace(f"License {m.group(1)}", id_tag)

    # Ensure ", LPC" credential is present immediately after the name.
    if f"{name}, LPC" not in result:
        if f"{name}," in result:
            # Name followed by something else (e.g. degree) — insert LPC.
            result = result.replace(f"{name},", f"{name}, LPC,", 1)
        else:
            # Standalone name span.
            result = result.replace(name, f"{name}, LPC", 1)

    # Ensure the license ID tag is present.
    if id_tag not in result:
        result = result.replace(f"{name}, LPC", f"{name}, LPC, {id_tag}", 1)

    # For signature spans: reconstruct from scratch to strip all intermediate text.
    result = _clean_signature_span(result, name, "LPC", lpc_id)

    return result if result != text else None


def _find_supervisor_span_fixes(page: "fitz.Page", name: str, lpc_id: str) -> list[dict]:
    """Return redact+reinsert dicts for every span on page that contains the supervisor name."""
    results = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                new_text = _fix_supervisor_span(span["text"], name, lpc_id)
                if new_text is not None:
                    results.append({
                        "rect":     fitz.Rect(span["bbox"]),
                        "origin":   fitz.Point(span["origin"]),
                        "new_text": new_text,
                        "size":     span["size"],
                    })
    return results


_SMALL_CAPS = str.maketrans({
    'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E', 'ɢ': 'G',
    'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J', 'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M',
    'ɴ': 'N', 'ᴏ': 'O', 'ᴘ': 'P', 'ʀ': 'R', 'ᴛ': 'T', 'ᴜ': 'U',
    'ᴠ': 'V', 'ᴡ': 'W', 'ʏ': 'Y', 'ᴢ': 'Z',
})


def _normalize_text(text: str) -> str:
    """Replace Unicode small-caps with plain ASCII so Helvetica renders them."""
    return text.translate(_SMALL_CAPS)


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
    Returns the number of pages written.
    """
    source = fitz.open(pdf_path)
    supervisors = supervisors or {}

    if pages_to_include is None:
        pages_to_include = set(range(len(source)))

    # Build new PDF with only the selected source pages; track index remapping.
    out = fitz.open()
    src_to_out: dict[int, int] = {}
    for src_idx in sorted(pages_to_include):
        out_idx = len(out)
        out.insert_pdf(source, from_page=src_idx, to_page=src_idx)
        src_to_out[src_idx] = out_idx
    source.close()

    pages_modified = 0
    for src_idx, out_idx in src_to_out.items():
        page = out[out_idx]
        spans: list[dict] = []

        if src_idx in corrections:
            clinician, old_title, new_title, new_id = corrections[src_idx]
            if old_title:
                spans += _find_affected_spans(
                    page, f"{clinician}, {old_title}", f"{clinician}, {new_title}", new_id
                )
            else:
                spans += _find_insert_spans(page, clinician, new_title, new_id)

        for sup_name, lpc_id in supervisors.items():
            spans += _find_supervisor_span_fixes(page, sup_name, lpc_id)

        if not spans:
            continue

        for s in spans:
            page.add_redact_annot(s["rect"], fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)

        for s in spans:
            page.insert_text(
                s["origin"],
                _normalize_text(s["new_text"]),
                fontname="helv",
                fontsize=s["size"],
                color=(0, 0, 0),
            )
        pages_modified += 1

    out.save(output_path)
    out.close()
    return pages_modified


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
