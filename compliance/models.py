"""Shared data model for the compliance engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Literal

DocumentType = Literal[
    "intake",
    "progress",
    "consultation",
    "treatment_plan",
    "discharge",
    "group",
    "family",
    "other",
]


@dataclass
class Page:
    index: int                    # 0-based within source PDF
    text: str
    page_num_in_note: int         # from "Page X of Y"
    page_total_in_note: int


@dataclass
class HeaderFields:
    service_date: date | None = None
    duration_minutes: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    clinician: str | None = None
    clinician_credential: str | None = None
    license_state: str | None = None
    license_id: str | None = None
    member_name: str | None = None
    member_id: str | None = None
    member_dob: date | None = None
    location: str | None = None
    service_code: str | None = None
    participants: list[str] = field(default_factory=list)
    supervisor: str | None = None
    entry_date: date | None = None


@dataclass
class Note:
    source_pdf: Path
    page_indices: list[int]               # pages from the source PDF making up this note
    pages: list[Page]
    note_type: DocumentType
    header: HeaderFields
    sections: dict[str, str]              # section_name (lowercase) → body text
    full_text: str

    @property
    def first_page_text(self) -> str:
        return self.pages[0].text if self.pages else ""

    @property
    def last_page_text(self) -> str:
        return self.pages[-1].text if self.pages else ""


@dataclass
class ContextBundle:
    """A member's notes for the same episode, used by cross-note checks."""
    member_name: str
    notes: list[Note]

    def of_type(self, doc_type: DocumentType) -> list[Note]:
        return [n for n in self.notes if n.note_type == doc_type]
