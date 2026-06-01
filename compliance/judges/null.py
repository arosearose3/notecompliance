"""
NullJudge — ships with V1.

Every judgment call returns manual_review so the engine runs end-to-end
without an LLM dependency. Replace by wiring in ClaudeJudge or LocalJudge.
"""

from __future__ import annotations

from compliance.judges.base import JudgeAnswer


class NullJudge:
    name = "null"

    def evaluate(
        self,
        *,
        question: str,
        context: str,
        hint: str = "",
    ) -> JudgeAnswer:
        return JudgeAnswer(
            verdict="manual_review",
            rationale="LLM judge not configured — requires human review.",
        )
