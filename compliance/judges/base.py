"""Judge protocol — pluggable interface for LLM-based evaluations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Judge(Protocol):
    name: str

    def evaluate(
        self,
        *,
        question: str,
        context: str,
        hint: str = "",
    ) -> "JudgeAnswer": ...


class JudgeAnswer:
    """Structured response from a judge."""

    def __init__(
        self,
        verdict: str,       # "pass" | "fail" | "not_applicable" | "manual_review"
        rationale: str,
        excerpts: list[str] | None = None,
    ) -> None:
        self.verdict = verdict
        self.rationale = rationale
        self.excerpts: list[str] = excerpts or []
