"""
Ingest PDFs and split multi-note files into individual Note objects.

Boundary signal: "Page X of Y" at the end of a page's extracted text.
When X == 1, a new note starts.  When X == Y, the note ends.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
except ImportError as e:
    raise ImportError("pdfplumber required: pip install pdfplumber") from e

from compliance.classify import assign_type
from compliance.extract.header import extract_header
from compliance.extract.sections import extract_sections
from compliance.models import HeaderFields, Note, Page

RE_PAGE_NUM = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)\s*$", re.MULTILINE)
RE_NOTE_TYPE_HEADER = re.compile(
    r"^((?:[A-Z][a-zA-Z]+ )*(?:[A-Z][a-zA-Z]+)\s+Note)\s*$",
    re.MULTILINE,
)


def _extract_note_type_header(text: str) -> str:
    m = RE_NOTE_TYPE_HEADER.search(text)
    return m.group(1).strip() if m else ""


def split_notes(pdf_path: Path) -> list[Note]:
    """
    Parse a PDF and return one Note per clinical note found.
    Multi-note PDFs are split on the Page-1-of-N boundary.
    """
    notes: list[Note] = []
    current_pages: list[Page] = []
    current_indices: list[int] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for raw_idx, pdf_page in enumerate(pdf.pages):
            text = pdf_page.extract_text() or ""
            m = RE_PAGE_NUM.search(text)
            if not m:
                # Pages without a page-number stamp are appended to current note
                if current_pages:
                    current_pages.append(Page(
                        index=raw_idx,
                        text=text,
                        page_num_in_note=len(current_pages) + 1,
                        page_total_in_note=-1,  # unknown
                    ))
                    current_indices.append(raw_idx)
                continue

            page_num   = int(m.group(1))
            page_total = int(m.group(2))

            if page_num == 1:
                # Save the previous note if any
                if current_pages:
                    notes.append(_build_note(pdf_path, current_indices, current_pages))
                current_pages = []
                current_indices = []

            current_pages.append(Page(
                index=raw_idx,
                text=text,
                page_num_in_note=page_num,
                page_total_in_note=page_total,
            ))
            current_indices.append(raw_idx)

    if current_pages:
        notes.append(_build_note(pdf_path, current_indices, current_pages))

    return notes


def _build_note(pdf_path: Path, page_indices: list[int], pages: list[Page]) -> Note:
    first_text = pages[0].text
    last_text  = pages[-1].text
    full_text  = "\n".join(p.text for p in pages)

    header = extract_header(first_text)
    # Supplement header with license info from last page
    last_header = extract_header(last_text)
    if last_header.license_state and not header.license_state:
        header.license_state = last_header.license_state
        header.license_id    = last_header.license_id
    if last_header.entry_date and not header.entry_date:
        header.entry_date = last_header.entry_date

    sections = extract_sections(full_text)

    note_type_str = _extract_note_type_header(first_text)
    doc_type = assign_type(note_type_str, header.service_code)

    return Note(
        source_pdf=pdf_path,
        page_indices=page_indices,
        pages=pages,
        note_type=doc_type,
        header=header,
        sections=sections,
        full_text=full_text,
    )


def ingest_directory(input_dir: Path) -> list[Note]:
    """Return all notes from all PDFs in input_dir (sorted by filename)."""
    all_notes: list[Note] = []
    for pdf_path in sorted(input_dir.glob("*.pdf")):
        all_notes.extend(split_notes(pdf_path))
    return all_notes
