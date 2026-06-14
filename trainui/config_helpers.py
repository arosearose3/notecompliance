"""Effective config helpers: merge code defaults with user-editable overrides."""

from __future__ import annotations

from compliance import config as cfg
from compliance.ruleset import get_ruleset


def effective_synonyms() -> dict[str, list[str]]:
    from compliance.extract.sections import SECTION_SYNONYMS
    merged = {k: list(v) for k, v in SECTION_SYNONYMS.items()}
    for canon, syns in cfg.get_section_synonyms().items():
        if isinstance(syns, list):
            merged[canon] = syns
    return merged


def effective_matrix(ruleset_id: str | None = None) -> dict[str, dict[str, str | None]]:
    """Return the fully resolved applicability matrix for the given ruleset."""
    rs = get_ruleset(ruleset_id)
    result: dict[str, dict[str, str | None]] = {}
    for sid in rs.standard_order:
        row = rs._matrix.get(sid, {})
        result[sid] = dict(row)
    return result
