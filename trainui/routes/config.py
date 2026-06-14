"""Tier 1 config routes: synonyms, applicability, thresholds (per-ruleset)."""

from __future__ import annotations

import yaml
from flask import Blueprint, current_app, jsonify, request

from compliance import config as cfg
from trainui.config_helpers import effective_matrix, effective_synonyms

bp_config = Blueprint("config", __name__)


def _ruleset():
    return current_app.config["RULESET"]


@bp_config.route("/api/config/synonyms", methods=["GET", "POST"])
def api_synonyms():
    # section_synonyms is SHARED (EHR vocabulary, not per-payer)
    path = cfg.RULES_DIR / "section_synonyms.yaml"
    if request.method == "GET":
        return jsonify(effective_synonyms())
    body = request.get_json(force=True)
    if not isinstance(body, dict):
        return jsonify({"error": "expected dict"}), 400
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
    cfg.invalidate(path)
    from compliance.extract import sections as sec_mod
    sec_mod._PATTERN_CACHE.clear()
    return jsonify({"ok": True})


@bp_config.route("/api/config/applicability", methods=["GET", "POST"])
def api_applicability():
    rs   = _ruleset()
    path = rs.rules_dir / "applicability.yaml"
    if request.method == "GET":
        return jsonify(effective_matrix(rs.id))
    body = request.get_json(force=True)
    if not isinstance(body, dict):
        return jsonify({"error": "expected dict"}), 400
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
    cfg.invalidate(path)
    from compliance.ruleset import invalidate_ruleset_cache
    invalidate_ruleset_cache(rs.id)
    return jsonify({"ok": True})


@bp_config.route("/api/config/thresholds", methods=["GET", "POST"])
def api_thresholds():
    rs   = _ruleset()
    path = rs.rules_dir / "thresholds.yaml"
    if request.method == "GET":
        return jsonify(dict(rs._thresholds))
    body = request.get_json(force=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
    cfg.invalidate(path)
    from compliance.ruleset import invalidate_ruleset_cache
    invalidate_ruleset_cache(rs.id)
    return jsonify({"ok": True})
