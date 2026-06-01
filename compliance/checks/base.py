"""Check protocol and CheckResult dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note

Verdict = Literal["pass", "fail", "not_applicable", "manual_review"]


@dataclass(frozen=True)
class CheckResult:
    standard_id: str               # e.g. "A3.duration"
    verdict: Verdict
    rationale: str                 # short human-readable explanation
    excerpts: tuple[str, ...] = field(default_factory=tuple)
    page_numbers: tuple[int, ...] = field(default_factory=tuple)
    judge_used: str | None = None  # None = rule-only


def _result(
    standard_id: str,
    verdict: Verdict,
    rationale: str,
    excerpts: list[str] | None = None,
    pages: list[int] | None = None,
    judge: str | None = None,
) -> CheckResult:
    return CheckResult(
        standard_id=standard_id,
        verdict=verdict,
        rationale=rationale,
        excerpts=tuple(excerpts or []),
        page_numbers=tuple(pages or []),
        judge_used=judge,
    )


def passed(standard_id: str, rationale: str = "Present.", **kw) -> CheckResult:
    return _result(standard_id, "pass", rationale, **kw)


def failed(standard_id: str, rationale: str, **kw) -> CheckResult:
    return _result(standard_id, "fail", rationale, **kw)


def not_applicable(standard_id: str, rationale: str = "Not applicable for this note type.") -> CheckResult:
    return _result(standard_id, "not_applicable", rationale)


def manual_review(standard_id: str, rationale: str = "Requires human review.") -> CheckResult:
    return _result(standard_id, "manual_review", rationale)


class Check(Protocol):
    standard_id: str

    def run(
        self,
        note: "Note",
        judge: "Judge",
        bundle: "ContextBundle | None" = None,
    ) -> CheckResult: ...
