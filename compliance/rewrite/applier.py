"""
Shared applier: consumes a RewritePlan and writes a corrected PDF.

This is the single place that touches fitz writes. Actions only locate and
transform; they never call fitz save/redact directly. This keeps the
dangerous part (modifying PDF bytes) in one audited place.

Invariant: source PDF is never modified. Output is always written to a
distinct path supplied by the caller.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError as e:
    raise ImportError("PyMuPDF (fitz) is required: pip install pymupdf") from e

from compliance.rewrite.types import RewritePlan, RewriteResult

_SMALL_CAPS = str.maketrans({
    'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E', 'ɢ': 'G',
    'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J', 'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M',
    'ɴ': 'N', 'ᴏ': 'O', 'ᴘ': 'P', 'ʀ': 'R', 'ᴛ': 'T', 'ᴜ': 'U',
    'ᴠ': 'V', 'ᴡ': 'W', 'ʏ': 'Y', 'ᴢ': 'Z',
})


def _normalize(text: str) -> str:
    """Replace Unicode small-caps with plain ASCII so Helvetica renders them."""
    return text.translate(_SMALL_CAPS)


def apply_plan(
    source_pdf: Path,
    output_pdf: Path,
    plan: RewritePlan,
    *,
    pages_to_include: set[int] | None = None,
    action_id: str = "unknown",
    note_meta: dict[str, Any] | None = None,
    standard_id: str | None = None,
    operator: str = "trainstandards",
) -> RewriteResult:
    """
    Write a corrected copy of source_pdf to output_pdf applying plan.

    If pages_to_include is None, all pages are copied.
    The source PDF is never modified.
    Returns a RewriteResult with the audit manifest.
    """
    if source_pdf.resolve() == output_pdf.resolve():
        raise ValueError(
            "output_pdf must differ from source_pdf — originals must never be modified"
        )

    src = fitz.open(str(source_pdf))

    if pages_to_include is None:
        pages_to_include = set(range(len(src)))

    out = fitz.open()
    src_to_out: dict[int, int] = {}
    for src_idx in sorted(pages_to_include):
        out_idx = len(out)
        out.insert_pdf(src, from_page=src_idx, to_page=src_idx)
        src_to_out[src_idx] = out_idx
    src.close()

    # Group plan entries by page_index for efficient per-page application
    by_page: dict[int, list[tuple]] = {}
    for span, new_text in plan.entries:
        by_page.setdefault(span.page_index, []).append((span, new_text))

    spans_changed = 0
    overflow_flags = plan.overflow_flags()
    manifest_spans = []

    for entry_idx, (span, new_text) in enumerate(plan.entries):
        out_idx = src_to_out.get(span.page_index)
        if out_idx is None:
            continue

        page = out[out_idx]
        rect = fitz.Rect(span.rect)
        origin = fitz.Point(span.origin)
        normalized = _normalize(new_text)

        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)
        page.insert_text(
            origin,
            normalized,
            fontname="helv",
            fontsize=span.size,
            color=(0, 0, 0),
        )
        spans_changed += 1

        overflow = overflow_flags[entry_idx] if entry_idx < len(overflow_flags) else False
        manifest_spans.append({
            "page_index": span.page_index,
            "old_text": span.old_text,
            "new_text": new_text,
            "overflow": overflow,
        })

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(output_pdf))
    out.close()

    manifest: dict[str, Any] = {
        "source_pdf": source_pdf.name,
        "output_pdf": output_pdf.name,
        "applied_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action_id,
        "note": note_meta or {},
        "spans": manifest_spans,
        "remediated_standard": standard_id,
        "operator": operator,
    }

    manifest_path = output_pdf.with_suffix(".rewrite.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return RewriteResult(
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        spans_changed=spans_changed,
        manifest=manifest,
    )
