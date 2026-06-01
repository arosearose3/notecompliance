"""
Applicability matrix — encodes which standards apply to which document types.

Values:
  "R"  required
  "C"  conditional (check may return not_applicable based on runtime facts)
  None not applicable; check must not run
"""

from __future__ import annotations

MATRIX: dict[str, dict[str, str | None]] = {
    # standard_id: {doc_type: "R" | "C" | None}
    "A1": {
        "intake": "R", "progress": "R", "consultation": "R",
        "treatment_plan": "R", "discharge": "R", "group": "R", "family": "R",
    },
    "A2": {
        "intake": "R",
    },
    "A3": {
        "intake": "R", "progress": "R", "consultation": "R", "discharge": "R",
        "group": "R", "family": "R",
    },
    "A4": {
        "progress": "C", "group": "R",
    },
    "A5": {
        "progress": "C", "family": "R",
    },
    "B1": {
        "intake": "C", "progress": "C", "consultation": "C",
        "treatment_plan": "C", "discharge": "C", "group": "C", "family": "C",
    },
    "B2": {},  # always manual_review — handled specially
    "C1": {
        "intake": "R", "progress": "C", "discharge": "R",
    },
    "C2a": {
        "intake": "C", "progress": "C", "discharge": "C",
    },
    "C2b": {
        "intake": "C", "progress": "C", "discharge": "C",
    },
    "C2c": {
        "intake": "C", "progress": "C", "discharge": "C",
    },
    "C2d": {
        "intake": "C", "progress": "C", "discharge": "C",
    },
    "C2e": {
        "discharge": "R",
    },
    "D1": {
        "intake": "R", "consultation": "C",
    },
    "D2": {
        "intake": "R", "progress": "C", "consultation": "C",
    },
    "D3": {
        "intake": "R",
    },
    "D4": {
        "intake": "R",
    },
    "D5": {
        "intake": "C",
    },
    "D6": {
        "intake": "C",
    },
    "D7": {
        "intake": "C",
    },
    "D8": {
        "intake": "R",
    },
    "D9": {
        "intake": "R",
    },
    "E1": {
        "treatment_plan": "R",
    },
    "E2": {
        "treatment_plan": "R",
    },
    "E3": {
        "treatment_plan": "R",
    },
    "E4": {
        "treatment_plan": "R",
    },
    "E5": {
        "treatment_plan": "R",
    },
    "E6": {
        "treatment_plan": "R",
    },
    "E7": {
        "treatment_plan": "R",
    },
    "E8": {
        "treatment_plan": "R",
    },
    "E9": {
        "treatment_plan": "R",
    },
    "E10": {
        "treatment_plan": "R",
    },
    "F1": {
        "progress": "R", "discharge": "R", "group": "R", "family": "R",
    },
    "F2": {
        "intake": "R", "progress": "R", "consultation": "R",
        "treatment_plan": "R", "discharge": "R", "group": "R", "family": "R",
    },
    "F3": {
        "intake": "C", "progress": "C", "consultation": "C",
        "treatment_plan": "C", "discharge": "C", "group": "C", "family": "C",
    },
    "F4": {
        "progress": "R", "group": "R", "family": "R",
    },
    "F5": {
        "progress": "R", "group": "R", "family": "R",
    },
    "F6": {
        "progress": "R", "group": "R", "family": "R",
    },
    "F7": {
        "progress": "C", "group": "C", "family": "C",
    },
    "F8": {
        "intake": "C", "progress": "R", "consultation": "C",
        "group": "R", "family": "R",
    },
    "G1": {
        "intake": "R", "treatment_plan": "R", "progress": "C",
    },
    "H1": {
        "discharge": "R",
    },
    "H2": {
        "discharge": "R",
    },
    "H3": {
        "discharge": "R",
    },
    "I1": {
        "intake": "R", "consultation": "R", "discharge": "R", "progress": "C",
    },
    "I2": {
        "intake": "R", "consultation": "R", "discharge": "R",
    },
    "J1": {
        "intake": "C", "progress": "C", "consultation": "C",
        "discharge": "C", "group": "C", "family": "C",
    },
    "K1": {
        "intake": "C", "progress": "C", "consultation": "C",
        "treatment_plan": "C", "discharge": "C", "group": "C", "family": "C",
    },
    "K2": {},  # always manual_review
}

ALL_DOC_TYPES = frozenset(
    ["intake", "progress", "consultation", "treatment_plan",
     "discharge", "group", "family", "other"]
)


def applies(standard_id: str, doc_type: str) -> str | None:
    """
    Return "R", "C", or None for the given standard and document type.
    None means the check should not run (not applicable).
    Config overrides in rules/applicability.yaml take precedence over MATRIX.
    """
    try:
        from compliance.config import get_applicability_overrides
        overrides = get_applicability_overrides()
        if standard_id in overrides:
            row = overrides[standard_id]
            if isinstance(row, dict) and doc_type in row:
                return row[doc_type]
    except Exception:
        pass
    return MATRIX.get(standard_id, {}).get(doc_type)


def get_applicable_standards(doc_type: str) -> list[str]:
    """Return all standard IDs that have any applicability for the given doc type."""
    return [sid for sid, row in MATRIX.items() if doc_type in row]
