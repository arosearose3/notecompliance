"""Tier 1 config routes: synonyms, applicability, thresholds."""

from __future__ import annotations

import yaml
from flask import Blueprint, jsonify, request

from compliance import config as cfg
from trainui.config_helpers import effective_matrix, effective_synonyms

bp_config = Blueprint("config", __name__)


@bp_config.route("/api/config/synonyms", methods=["GET", "POST"])
def api_synonyms():
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
    path = cfg.RULES_DIR / "applicability.yaml"
    if request.method == "GET":
        return jsonify(effective_matrix())
    body = request.get_json(force=True)
    if not isinstance(body, dict):
        return jsonify({"error": "expected dict"}), 400
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
    cfg.invalidate(path)
    return jsonify({"ok": True})


@bp_config.route("/api/config/thresholds", methods=["GET", "POST"])
def api_thresholds():
    path = cfg.RULES_DIR / "thresholds.yaml"
    if request.method == "GET":
        return jsonify(cfg.get_thresholds())
    body = request.get_json(force=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
    cfg.invalidate(path)
    return jsonify({"ok": True})
