"""Effective config helpers: merge code defaults with user-editable overrides."""

from __future__ import annotations

from compliance import config as cfg


def effective_synonyms() -> dict[str, list[str]]:
    from compliance.extract.sections import SECTION_SYNONYMS
    merged = {k: list(v) for k, v in SECTION_SYNONYMS.items()}
    for canon, syns in cfg.get_section_synonyms().items():
        if isinstance(syns, list):
            merged[canon] = syns
    return merged


def effective_matrix() -> dict[str, dict[str, str | None]]:
    from compliance.applicability import MATRIX
    import copy
    merged = copy.deepcopy(MATRIX)
    for sid, row in cfg.get_applicability_overrides().items():
        if sid in merged:
            merged[sid].update(row)
        else:
            merged[sid] = row
    return merged
