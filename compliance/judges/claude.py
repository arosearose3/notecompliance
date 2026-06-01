"""
ClaudeJudge — Anthropic API judge (Phase 4, gated on Q-LLM-1 / Q-LLM-2).

Requires:
  pip install anthropic
  ANTHROPIC_API_KEY environment variable

This module is intentionally not imported at package level so V1 has no
Anthropic dependency. Wire it in via --judge claude at the CLI.

PHI WARNING: Enabling this judge sends note text to the Anthropic API.
Ensure a BAA is in place (Q-LLM-2) before use in production.
"""

from __future__ import annotations

import os

from compliance.judges.base import JudgeAnswer

_SYSTEM = """\
You are a clinical documentation compliance reviewer. You will be given a
question about whether a specific clinical note meets a documentation standard,
and the relevant note text as context. Answer with a JSON object:
{
  "verdict": "pass" | "fail" | "not_applicable" | "manual_review",
  "rationale": "one or two sentences explaining the verdict",
  "excerpts": ["relevant quote from the note", ...]
}
Respond with the JSON object only — no prose outside it.
"""


class ClaudeJudge:
    name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package required for ClaudeJudge: pip install anthropic"
            ) from e
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def evaluate(
        self,
        *,
        question: str,
        context: str,
        hint: str = "",
    ) -> JudgeAnswer:
        import json

        prompt = f"Standard question: {question}\n\nNote text:\n{context}"
        if hint:
            prompt += f"\n\nHint: {hint}"

        msg = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        try:
            data = json.loads(raw)
            return JudgeAnswer(
                verdict=data.get("verdict", "manual_review"),
                rationale=data.get("rationale", ""),
                excerpts=data.get("excerpts", []),
            )
        except (json.JSONDecodeError, KeyError):
            return JudgeAnswer(
                verdict="manual_review",
                rationale=f"Judge response parse error: {raw[:200]}",
            )
