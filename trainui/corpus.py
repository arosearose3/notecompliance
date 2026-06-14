"""Regression corpus persistence helpers (per-ruleset)."""

from __future__ import annotations

import json
from pathlib import Path

from trainui.paths import CORPUS_PATH


def corpus_path_for(ruleset_id: str | None = None) -> Path:
    """Return the corpus.json path for the given ruleset (defaults to legacy path)."""
    if ruleset_id:
        from trainui.paths import RULES_DIR
        return RULES_DIR / ruleset_id / "corpus.json"
    return CORPUS_PATH


def load_corpus(ruleset_id: str | None = None) -> list:
    p = corpus_path_for(ruleset_id)
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_corpus(corpus: list, ruleset_id: str | None = None) -> None:
    p = corpus_path_for(ruleset_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
