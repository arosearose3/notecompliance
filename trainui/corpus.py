"""Regression corpus persistence helpers."""

from __future__ import annotations

import json

from trainui.paths import CORPUS_PATH


def load_corpus() -> list:
    if not CORPUS_PATH.is_file():
        return []
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def save_corpus(corpus: list) -> None:
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
