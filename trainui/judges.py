"""Judge wrappers used by the training UI."""

from __future__ import annotations

from compliance.judges.base import JudgeAnswer
from compliance import config as cfg


class SkipJudge:
    """
    Judge that immediately returns 'skipped' without calling any LLM.
    Used when --no-ai is set so judgment-based checks complete instantly
    and the card clearly indicates they were not evaluated.
    """
    name = "skip"

    def evaluate(self, *, question: str, context: str, hint: str = "") -> JudgeAnswer:
        return JudgeAnswer(
            verdict="skipped",
            rationale="AI judge disabled (--no-ai). Re-run without --no-ai to evaluate.",
        )


class ConfigurableRecordingJudge:
    """
    Wraps any Judge, substitutes per-standard prompt overrides from
    rules/prompts/<id>.md at call time, and records every evaluate() call.
    """

    def __init__(self, inner: object, standard_id: str) -> None:
        self._inner = inner
        self._sid = standard_id
        self.name: str = f"recording({getattr(inner, 'name', '?')})"
        self.calls: list[dict] = []

    def evaluate(self, *, question: str, context: str, hint: str = "") -> JudgeAnswer:
        override = cfg.get_prompt(self._sid)
        effective_q = override if override else question
        answer = self._inner.evaluate(question=effective_q, context=context, hint=hint)
        self.calls.append({
            "question":           question,
            "effective_question": effective_q,
            "prompt_overridden":  override is not None,
            "context":            context[:800],
            "verdict":            answer.verdict,
            "rationale":          answer.rationale,
            "excerpts":           answer.excerpts,
        })
        return answer
