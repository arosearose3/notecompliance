"""
Classify a raw note into a DocumentType.

Priority order:
1. Service code (most authoritative)
2. Note-type header text
3. Note-type keywords in first-page text
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compliance.models import DocumentType

# CPT code sets
_GROUP_CPT  = frozenset(["90853", "90849", "90857"])
_FAMILY_CPT = frozenset(["90847", "90846"])

# Header type patterns (match the "Note Type" line)
_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btelehealth\b", re.IGNORECASE), "progress"),  # check before generic progress
    (re.compile(r"\bintake\b", re.IGNORECASE),               "intake"),
    (re.compile(r"\bconsultation\b", re.IGNORECASE),          "consultation"),
    (re.compile(r"\btreatment\s+plan\b", re.IGNORECASE),      "treatment_plan"),
    (re.compile(r"\bdischarge\b", re.IGNORECASE),             "discharge"),
    (re.compile(r"\bgroup\b", re.IGNORECASE),                 "group"),
    (re.compile(r"\bfamily\b", re.IGNORECASE),                "family"),
    (re.compile(r"\bprogress\b", re.IGNORECASE),              "progress"),
]


def assign_type(note_type_header: str, service_code: str | None) -> "DocumentType":
    """
    Given the raw note-type header string and CPT code, return a DocumentType.
    """
    code = (service_code or "").strip()

    if code in _GROUP_CPT:
        return "group"
    if code in _FAMILY_CPT:
        return "family"

    header = (note_type_header or "").strip()
    for pattern, doc_type in _TYPE_PATTERNS:
        if pattern.search(header):
            return doc_type  # type: ignore[return-value]

    return "other"
