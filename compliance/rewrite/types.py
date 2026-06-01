"""Shared data types for the rewrite engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TargetSpan:
    """A single text span located in a PDF page, candidate for replacement."""
    page_index: int          # 0-based index in the source PDF
    rect: tuple              # (x0, y0, x1, y1) bounding box
    origin: tuple            # (x, y) text insertion origin
    size: float              # font size in points
    font: str                # font name as reported by fitz
    old_text: str            # verbatim span text as extracted


@dataclass
class RewritePlan:
    """Ordered list of span replacements across a note's pages."""
    entries: list[tuple[TargetSpan, str]] = field(default_factory=list)
    # Each entry: (span, new_text)

    def add(self, span: TargetSpan, new_text: str) -> None:
        self.entries.append((span, new_text))

    def overflow_flags(self) -> list[bool]:
        """
        Estimate overflow for each entry: True when new text is wider than
        the original span's bounding box.

        Uses a rough character-width heuristic (0.6 × font_size per character)
        since we don't have the actual glyph metrics here. The applier uses
        Helvetica, so this approximation is reasonable for ASCII.
        """
        result = []
        for span, new_text in self.entries:
            span_width = span.rect[2] - span.rect[0]
            est_new_width = len(new_text) * span.size * 0.6
            result.append(est_new_width > span_width)
        return result


@dataclass
class RewriteResult:
    """Result returned after successfully applying a RewritePlan."""
    source_pdf: Path
    output_pdf: Path
    spans_changed: int
    manifest: dict[str, Any]
