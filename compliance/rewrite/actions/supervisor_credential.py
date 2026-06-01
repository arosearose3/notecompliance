"""
Rewrite action: supervisor_credential

Normalises the supervisor's credential in header and signature spans:
  - Ensures ", LPC" appears immediately after the supervisor's name
  - Normalises "License CO NNNNN" / "License NNNNN" to "#NNNNN"
  - Reconstructs signature spans ("signed this note") from scratch

Extracted from fixtnpdf._find_supervisor_span_fixes / _fix_supervisor_span.
"""

from __future__ import annotations

import re
from typing import Any

try:
    import fitz
except ImportError as e:
    raise ImportError("PyMuPDF (fitz) is required: pip install pymupdf") from e

from compliance.rewrite.types import TargetSpan


RE_LICENSE         = re.compile(r"License ([A-Z]{2}) (\d+)")
RE_LICENSE_NOSTATE = re.compile(r"License (\d+)")
RE_SIGNED          = re.compile(r",?\s*signed\s+this\s+note", re.IGNORECASE)


def _clean_signature_span(text: str, name: str, credential: str, lpc_id: str | None) -> str:
    if "signed this note" not in text.lower() or name not in text:
        return text
    prefix = text[: text.index(name)]
    signed_m = RE_SIGNED.search(text)
    if not signed_m:
        return text
    suffix = text[signed_m.end():]
    cred_part = f"{credential}, #{lpc_id}" if lpc_id else credential
    return f"{prefix}{name}, {cred_part}, signed this note{suffix}"


def _fix_supervisor_text(text: str, name: str, lpc_id: str) -> str | None:
    if name not in text:
        return None

    result = text
    id_tag = f"#{lpc_id}"

    m = RE_LICENSE.search(result)
    if m:
        result = result.replace(f"License {m.group(1)} {m.group(2)}", id_tag)
    else:
        m = RE_LICENSE_NOSTATE.search(result)
        if m:
            result = result.replace(f"License {m.group(1)}", id_tag)

    if f"{name}, LPC" not in result:
        if f"{name}," in result:
            result = result.replace(f"{name},", f"{name}, LPC,", 1)
        else:
            result = result.replace(name, f"{name}, LPC", 1)

    if id_tag not in result:
        result = result.replace(f"{name}, LPC", f"{name}, LPC, {id_tag}", 1)

    result = _clean_signature_span(result, name, "LPC", lpc_id)

    return result if result != text else None


class SupervisorCredentialAction:
    id = "supervisor_credential"
    label = "Normalise supervisor credential (LPC + license ID)"
    scope = "note"
    applies_to: list[str] = []  # all doc types
    params = [
        {
            "name": "supervisors_csv",
            "label": "Supervisors CSV path",
            "type": "file",
            "required": True,
            "default": "supervisors.csv",
        }
    ]

    def locate(self, fitz_page: Any, note: Any, params: dict) -> list[TargetSpan]:
        supervisor_data = params.get("_supervisor_data") or {}
        spans = []
        for name, lpc_id in supervisor_data.items():
            for block in fitz_page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        new_text = _fix_supervisor_text(span["text"], name, lpc_id)
                        if new_text is not None:
                            spans.append(TargetSpan(
                                page_index=fitz_page.number,
                                rect=tuple(span["bbox"]),
                                origin=tuple(span["origin"]),
                                size=span["size"],
                                font=span.get("font", "helv"),
                                old_text=span["text"],
                            ))
        return spans

    def transform(self, span: TargetSpan, note: Any, params: dict, data: Any) -> str | None:
        supervisor_data = params.get("_supervisor_data") or {}
        for name, lpc_id in supervisor_data.items():
            if name in span.old_text:
                return _fix_supervisor_text(span.old_text, name, lpc_id)
        return None
