"""
Action registry for the rewrite engine.

A RewriteAction is a Python object with:
  id      : str
  label   : str
  scope   : "note" | "page" | "document"
  params  : list[dict] — parameter schema for the UI
  applies_to : list[str] — doc types this action may target ([] = all)

  locate(fitz_page, note, params) -> list[TargetSpan]
      Walk fitz get_text("dict") and return spans to change.

  transform(span, note, params, data) -> str | None
      Compute replacement string. None = leave span unchanged.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from compliance.rewrite.types import TargetSpan


@runtime_checkable
class RewriteAction(Protocol):
    id: str
    label: str
    scope: str            # "note" | "page" | "document"
    params: list[dict]    # [{name, label, type, required, default}]
    applies_to: list[str] # doc_type strings; empty = all

    def locate(self, fitz_page: Any, note: Any, params: dict) -> list[TargetSpan]: ...
    def transform(self, span: TargetSpan, note: Any, params: dict, data: Any) -> str | None: ...


ACTION_REGISTRY: dict[str, RewriteAction] = {}


def register_action(action: RewriteAction) -> None:
    ACTION_REGISTRY[action.id] = action


def get_action(action_id: str) -> RewriteAction | None:
    return ACTION_REGISTRY.get(action_id)
