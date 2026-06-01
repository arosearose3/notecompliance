"""
Tier-R1 declarative rewrite actions.

Each entry in rules/rewrites.yaml becomes a DeclarativeRewriteAction at
runtime. The generic locator finds spans by matching an anchor string; the
generic transform fills a template with note header fields.

YAML schema for one entry:
  id: telehealth_modifier            # stable identifier
  label: "Add telehealth statement"  # UI label
  match:
    pattern: "signed this note"      # text that must appear in the span
  replace:
    template: "{clinician}, {credential}, telehealth session, signed this note"
  applies_to: [progress, consultation]   # [] or absent = all doc types

Template variables available (from note.header):
  {clinician}    {credential}    {member}    {service_date}
  {license_id}   {supervisor}    {location}  {service_code}
"""

from __future__ import annotations

from typing import Any

from compliance.rewrite.types import TargetSpan


class DeclarativeRewriteAction:
    """A runtime rewrite action constructed from a YAML config entry."""

    def __init__(self, entry: dict) -> None:
        self.id: str = entry["id"]
        self.label: str = entry.get("label", self.id)
        self.scope: str = entry.get("scope", "note")
        self.applies_to: list[str] = entry.get("applies_to") or []
        self._pattern: str = entry.get("match", {}).get("pattern", "")
        self._template: str = entry.get("replace", {}).get("template", "")
        self.params: list[dict] = []  # declarative actions have no runtime params

    def locate(self, fitz_page: Any, note: Any, params: dict) -> list[TargetSpan]:
        if not self._pattern:
            return []
        # Skip if action doesn't apply to this doc type
        if self.applies_to and note.note_type not in self.applies_to:
            return []

        spans = []
        for block in fitz_page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if self._pattern in span["text"]:
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
        if not self._template:
            return None
        h = note.header
        variables = {
            "clinician":    h.clinician or "",
            "credential":   h.clinician_credential or "",
            "member":       h.member_name or "",
            "service_date": str(h.service_date) if h.service_date else "",
            "license_id":   h.license_id or "",
            "supervisor":   h.supervisor or "",
            "location":     h.location or "",
            "service_code": h.service_code or "",
        }
        try:
            return self._template.format(**variables)
        except KeyError:
            return None


def load_declarative_actions() -> list[DeclarativeRewriteAction]:
    """Return all Tier-R1 actions from rules/rewrites.yaml (live-reloaded via mtime cache)."""
    from compliance import config as cfg
    return [DeclarativeRewriteAction(e) for e in cfg.get_rewrites()]
