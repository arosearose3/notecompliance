"""Tier 2 prompt routes: get, save, delete, test."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from compliance import config as cfg

bp_prompts = Blueprint("prompts", __name__)


@bp_prompts.route("/api/prompts/<standard_id>")
def api_get_prompt(standard_id: str):
    override = cfg.get_prompt(standard_id)
    return jsonify({"standard_id": standard_id, "prompt": override, "overridden": override is not None})


@bp_prompts.route("/api/prompts/<standard_id>/save", methods=["POST"])
def api_save_prompt(standard_id: str):
    body = request.get_json(force=True)
    prompt = body.get("prompt", "")
    path = cfg.RULES_DIR / "prompts" / f"{standard_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt, encoding="utf-8")
    cfg.invalidate(path)
    return jsonify({"ok": True})


@bp_prompts.route("/api/prompts/<standard_id>/delete", methods=["POST"])
def api_delete_prompt(standard_id: str):
    path = cfg.RULES_DIR / "prompts" / f"{standard_id}.md"
    path.unlink(missing_ok=True)
    cfg.invalidate(path)
    return jsonify({"ok": True})


@bp_prompts.route("/api/prompts/<standard_id>/test", methods=["POST"])
def api_test_prompt(standard_id: str):
    body     = request.get_json(force=True)
    question = body.get("question", "")
    context  = body.get("context", "")
    inner_judge = current_app.config["INNER_JUDGE"]
    try:
        answer = inner_judge.evaluate(question=question, context=context)
        return jsonify({"verdict": answer.verdict, "rationale": answer.rationale, "excerpts": answer.excerpts})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
