"""
compliance.rewrite — shared PDF-rewrite engine.

The engine has three layers:
  TargetSpan  — a located span (page index, bbox, origin, font size, old text)
  RewritePlan — ordered (TargetSpan, new_text) pairs across one note's pages
  RewriteAction — locator + transform, registered in the ACTION_REGISTRY
  apply_plan  — the single shared applier (redact rect → reinsert at origin)

Registered actions are discoverable by trainstandards.py via ACTION_REGISTRY.
"""

from compliance.rewrite.types import TargetSpan, RewritePlan, RewriteResult
from compliance.rewrite.applier import apply_plan
from compliance.rewrite.registry import ACTION_REGISTRY, register_action, get_action

__all__ = [
    "TargetSpan",
    "RewritePlan",
    "RewriteResult",
    "apply_plan",
    "ACTION_REGISTRY",
    "register_action",
    "get_action",
]
