"""
OllamaJudge — local-model judge using the Ollama generate API.

Requires Ollama to be running locally (default: http://localhost:11434).
No API key needed.  All note text stays on-machine — no PHI leaves the
network boundary.

Usage from trainstandards.py:
    from compliance.judges.ollama import OllamaJudge
    judge = OllamaJudge()            # uses qwen3.5:9b by default
    judge = OllamaJudge("mistral")   # any model installed in Ollama
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error

from compliance.judges.base import JudgeAnswer

_SYSTEM = """\
You are a clinical documentation compliance reviewer. You will be given a \
question about whether a specific clinical note meets a documentation standard, \
and the relevant note text as context.

Respond with a single JSON object and nothing else — no markdown fences, no \
prose before or after:
{"verdict":"pass"|"fail"|"not_applicable"|"manual_review",\
"rationale":"one or two sentences","excerpts":["relevant quote",...]}
"""

# Regex to extract the first {...} block from a response that may include
# chain-of-thought <think>...</think> tags or surrounding prose.
_JSON_RE = re.compile(r'\{[^{}]*"verdict"[^{}]*\}', re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks produced by reasoning models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class OllamaJudge:
    """Judge backed by a locally-running Ollama model."""

    def __init__(
        self,
        model: str = "qwen3.5:9b",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self.name = f"ollama:{model}"
        self._model = model
        self._url = f"{base_url.rstrip('/')}/api/generate"

    def evaluate(
        self,
        *,
        question: str,
        context: str,
        hint: str = "",
    ) -> JudgeAnswer:
        prompt = (
            f"{_SYSTEM}\n\n"
            f"Standard question: {question}\n\n"
            f"Note text:\n{context}"
        )
        if hint:
            prompt += f"\n\nHint: {hint}"

        payload = json.dumps({
            "model":  self._model,
            "prompt": prompt,
            "stream": False,
        }).encode()

        try:
            req  = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw_body = resp.read().decode()
        except urllib.error.URLError as exc:
            return JudgeAnswer(
                verdict="manual_review",
                rationale=f"Ollama unreachable: {exc}",
            )

        try:
            outer = json.loads(raw_body)
            raw   = outer.get("response", "")
        except json.JSONDecodeError:
            raw = raw_body

        # Strip chain-of-thought blocks if present
        raw = _strip_thinking(raw)

        # Try to parse the first JSON object in the response
        m = _JSON_RE.search(raw)
        if m:
            try:
                data = json.loads(m.group())
                return JudgeAnswer(
                    verdict=data.get("verdict", "manual_review"),
                    rationale=data.get("rationale", ""),
                    excerpts=data.get("excerpts", []),
                )
            except json.JSONDecodeError:
                pass

        return JudgeAnswer(
            verdict="manual_review",
            rationale=f"Could not parse Ollama response: {raw[:200]}",
        )
