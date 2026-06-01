"""
Rewrite action: provider_title

Corrects the rendering clinician's credential (Intern / LPCC / LPC) and
license ID in the page header and signature spans of a note.

Locator: finds spans containing "{clinician}, {old_title}" (or the bare
         clinician name when no credential is currently present).
Transform: computes the correct credential from the session date and
           licensure CSV data, then reconstructs the span text.

This is the direct generalisation of fixtnpdf.py's title-fix logic.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

try:
    import fitz
except ImportError as e:
    raise ImportError("PyMuPDF (fitz) is required: pip install pymupdf") from e

from compliance.rewrite.types import TargetSpan


RE_SIG_CRED  = re.compile(r",\s+(\S+)")
RE_LICENSE   = re.compile(r"License ([A-Z]{2}) (\d+)")
RE_SIGNED    = re.compile(r",?\s*signed\s+this\s+note", re.IGNORECASE)


def compute_credential(session_date: date, provider: dict) -> tuple[str, str | None]:
    """Return (title, license_id). license_id is None for Intern."""
    if provider.get("lpc") and session_date >= provider["lpc"]:
        return "LPC", provider.get("lpc_id") or None
    if provider.get("lpcc") and session_date >= provider["lpcc"]:
        return "LPCC", provider.get("lpcc_id") or None
    return "Intern", None


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


def _substitute_span_text(span_text: str, old_cred: str, new_cred: str, new_id: str | None) -> str:
    result = span_text.replace(old_cred, new_cred)
    if new_id is not None:
        m = RE_LICENSE.search(result)
        if m:
            result = result.replace(f"License {m.group(1)} {m.group(2)}", f"#{new_id}")
        elif new_cred in result:
            result = result.replace(new_cred, f"{new_cred}, #{new_id}", 1)
    if "signed this note" in result.lower():
        parts = new_cred.split(", ", 1)
        if len(parts) == 2:
            result = _clean_signature_span(result, parts[0], parts[1], new_id)
    return result


def _locate_affected(fitz_page, old_cred_text: str, new_cred_text: str, new_id: str | None) -> list[TargetSpan]:
    results = []
    for block in fitz_page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if old_cred_text in span["text"]:
                    new_text = _substitute_span_text(span["text"], old_cred_text, new_cred_text, new_id)
                    results.append(TargetSpan(
                        page_index=fitz_page.number,
                        rect=tuple(span["bbox"]),
                        origin=tuple(span["origin"]),
                        size=span["size"],
                        font=span.get("font", "helv"),
                        old_text=span["text"],
                    ))
    return results


def _locate_insert(fitz_page, clinician: str, new_title: str, new_id: str | None) -> list[TargetSpan]:
    """For notes where the credential was absent from the header."""
    results = []
    for block in fitz_page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"]
                stripped = text.strip()

                if stripped == clinician:
                    results.append(TargetSpan(
                        page_index=fitz_page.number,
                        rect=tuple(span["bbox"]),
                        origin=tuple(span["origin"]),
                        size=span["size"],
                        font=span.get("font", "helv"),
                        old_text=text,
                    ))
                    continue

                if clinician + "," in text:
                    after = text[text.index(clinician + ",") + len(clinician):]
                    m = RE_SIG_CRED.match(after)
                    if m:
                        existing_cred = m.group(1).rstrip(",")
                        if existing_cred != new_title:
                            results.append(TargetSpan(
                                page_index=fitz_page.number,
                                rect=tuple(span["bbox"]),
                                origin=tuple(span["origin"]),
                                size=span["size"],
                                font=span.get("font", "helv"),
                                old_text=text,
                            ))
    return results


class ProviderTitleAction:
    id = "provider_title"
    label = "Correct provider credential (Intern / LPCC / LPC)"
    scope = "note"
    applies_to: list[str] = []  # all doc types
    params = [
        {
            "name": "providers_csv",
            "label": "Licensure CSV path",
            "type": "file",
            "required": True,
            "default": "licensedates.csv",
        }
    ]

    def locate(self, fitz_page: Any, note: Any, params: dict) -> list[TargetSpan]:
        clinician = (note.header.clinician or "").strip()
        old_title = (note.header.clinician_credential or "").strip()
        if not clinician:
            return []

        data = params.get("_provider_data") or {}
        provider = data.get(clinician)
        if not provider or not note.header.service_date:
            return []

        new_title, new_id = compute_credential(note.header.service_date, provider)

        if old_title and old_title != new_title:
            return _locate_affected(
                fitz_page,
                f"{clinician}, {old_title}",
                f"{clinician}, {new_title}",
                new_id,
            )
        elif not old_title:
            return _locate_insert(fitz_page, clinician, new_title, new_id)
        return []

    def transform(self, span: TargetSpan, note: Any, params: dict, data: Any) -> str | None:
        clinician = (note.header.clinician or "").strip()
        old_title = (note.header.clinician_credential or "").strip()
        if not clinician:
            return None

        provider_data = params.get("_provider_data") or {}
        provider = provider_data.get(clinician)
        if not provider or not note.header.service_date:
            return None

        new_title, new_id = compute_credential(note.header.service_date, provider)

        if old_title and old_title != new_title:
            return _substitute_span_text(
                span.old_text,
                f"{clinician}, {old_title}",
                f"{clinician}, {new_title}",
                new_id,
            )
        elif not old_title:
            # Insert credential into bare-name span
            text = span.old_text
            stripped = text.strip()
            if stripped == clinician:
                cred_part = f"{clinician}, {new_title}, #{new_id}" if new_id else f"{clinician}, {new_title}"
                return text.replace(clinician, cred_part, 1)
            # Signature span with different credential
            if clinician + "," in text:
                after = text[text.index(clinician + ",") + len(clinician):]
                m = RE_SIG_CRED.match(after)
                if m:
                    existing_cred = m.group(1).rstrip(",")
                    old_sig = f"{clinician}, {existing_cred}"
                    new_sig = f"{clinician}, {new_title}"
                    return _substitute_span_text(text, old_sig, new_sig, new_id)
        return None
