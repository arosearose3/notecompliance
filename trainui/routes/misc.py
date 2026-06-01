"""Miscellaneous routes: generate-request, reload."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from compliance import config as cfg
from trainui.artifacts import build_request_artifact, read_check_source
from trainui.paths import RULE_REQUESTS_DIR

bp_misc = Blueprint("misc", __name__)


@bp_misc.route("/api/generate-request", methods=["POST"])
def api_generate_request():
    body   = request.get_json(force=True)
    sid    = body.get("standard_id", "unknown")
    ts     = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    source = read_check_source(sid)
    md     = build_request_artifact(body, source)
    RULE_REQUESTS_DIR.mkdir(exist_ok=True)
    fname  = f"{sid}_{ts}.md"
    (RULE_REQUESTS_DIR / fname).write_text(md, encoding="utf-8")
    return jsonify({"markdown": md, "file": str(RULE_REQUESTS_DIR / fname)})


@bp_misc.route("/api/reload", methods=["POST"])
def api_reload():
    cfg.invalidate()
    from compliance.extract import sections as sec_mod
    sec_mod._PATTERN_CACHE.clear()
    return jsonify({"ok": True})
