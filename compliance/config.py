"""
Config loader for the compliance engine's editable rule tables.

All editable config lives in rules/ at the repo root. Tables are read at
call-time and cached by file mtime so edits made through the UI (or a text
editor) are picked up on the next evaluation with no server restart.
"""

from __future__ import annotations

from pathlib import Path

try:
    import yaml as _yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

# rules/ is one level above this file (compliance/ → parent → rules/)
RULES_DIR = Path(__file__).parent.parent / "rules"

_CACHE: dict[str, tuple[float, object]] = {}  # path-str → (mtime, value)


def _load_yaml(path: Path) -> dict:
    if not _YAML_OK:
        return {}
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _CACHE.pop(key, None)
        return {}
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]  # type: ignore[return-value]
    with open(path, encoding="utf-8") as f:
        val = _yaml.safe_load(f) or {}
    if not isinstance(val, dict):
        val = {}
    _CACHE[key] = (mtime, val)
    return val


def _load_text(path: Path) -> str | None:
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _CACHE.pop(key, None)
        return None
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]  # type: ignore[return-value]
    val = path.read_text(encoding="utf-8").strip()
    _CACHE[key] = (mtime, val)
    return val


def invalidate(path: Path | None = None) -> None:
    """Invalidate one cached path (or the whole cache when path is None)."""
    if path is None:
        _CACHE.clear()
    else:
        _CACHE.pop(str(path), None)


# ── Public accessors ───────────────────────────────────────────────────────────

def get_section_synonyms() -> dict[str, list[str]]:
    """
    Return the config-defined section synonyms.
    When non-empty, a canonical key here fully replaces the code default for
    that key (config is the source of truth once written).
    """
    return _load_yaml(RULES_DIR / "section_synonyms.yaml")


def get_thresholds() -> dict[str, object]:
    """Return all numeric/string thresholds (e.g. late_entry_hours)."""
    return _load_yaml(RULES_DIR / "thresholds.yaml")


def get_threshold(key: str, default):
    """Return a single threshold value with a default."""
    return get_thresholds().get(key, default)


def get_applicability_overrides() -> dict[str, dict[str, str | None]]:
    """
    Return applicability overrides.  Keys are standard IDs; values are
    {doc_type: "R" | "C" | None}.  These override (not extend) the default
    MATRIX for any standard_id present here.
    """
    return _load_yaml(RULES_DIR / "applicability.yaml")


def get_prompt(standard_id: str) -> str | None:
    """Return the judge-prompt override for a standard, or None if unset."""
    return _load_text(RULES_DIR / "prompts" / f"{standard_id}.md")


def get_rewrites() -> list[dict]:
    """
    Return the list of Tier-R1 declarative rewrite actions from rules/rewrites.yaml.

    Each entry has: id, label, match (section/pattern), replace (template),
    applies_to (list of doc types, empty = all).
    """
    path = RULES_DIR / "rewrites.yaml"
    if not _YAML_OK:
        return []
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _CACHE.pop(key, None)
        return []
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]  # type: ignore[return-value]
    with open(path, encoding="utf-8") as f:
        val = _yaml.safe_load(f) or []
    if not isinstance(val, list):
        val = []
    _CACHE[key] = (mtime, val)
    return val
