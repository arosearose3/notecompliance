"""
Applicability — delegates to the active Ruleset.

The hardcoded MATRIX and standalone applies()/get_applicable_standards() are
kept for backward compatibility but now route through the Ruleset so both
functions always agree (fixes the pre-existing divergence where get_applicable_standards
read MATRIX only while applies() also consulted YAML overrides).

Prefer using ruleset.applies() and ruleset.get_applicable_standards() directly.
"""

from __future__ import annotations

from compliance.ruleset import get_ruleset, _DEFAULT_MATRIX, _ALL_DOC_TYPES

# Keep MATRIX importable for code that reads it directly (e.g. config_helpers.py)
MATRIX = _DEFAULT_MATRIX
ALL_DOC_TYPES = _ALL_DOC_TYPES


def applies(standard_id: str, doc_type: str) -> str | None:
    """
    Return "R", "C", or None for the given standard and document type.
    Delegates to the default ruleset so applies() and get_applicable_standards()
    always agree.
    """
    return get_ruleset().applies(standard_id, doc_type)


def get_applicable_standards(doc_type: str) -> list[str]:
    """Return all standard IDs that have any applicability for the given doc type."""
    return get_ruleset().get_applicable_standards(doc_type)
