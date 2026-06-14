"""Core routes: PDF list, evaluation, PDF serving."""

from __future__ import annotations

import json as _json

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

from compliance.ingest import split_notes
from trainui.evaluation import evaluate_pdf, evaluate_pdf_stream
from trainui.webutil import resolve_pdf

bp_core = Blueprint("core", __name__)


@bp_core.route("/api/pdfs")
def api_pdfs():
    source_dir = current_app.config["SOURCE_DIR"]
    pdfs = []
    for p in sorted(source_dir.glob("*.pdf")):
        try:
            count = len(split_notes(p))
        except Exception:
            count = 0
        pdfs.append({"name": p.name, "note_count": count})
    return jsonify({"source_dir": str(source_dir), "pdfs": pdfs})


@bp_core.route("/api/pdfs/stream")
def api_pdfs_stream():
    """SSE stream: emits one 'pdf' event per file as it is scanned."""
    from flask import Response, stream_with_context

    source_dir = current_app.config["SOURCE_DIR"]

    def generate():
        pdf_files = sorted(source_dir.glob("*.pdf"))
        total = len(pdf_files)
        yield f"event: start\ndata: {_json.dumps({'total': total, 'source_dir': str(source_dir)})}\n\n"
        for i, p in enumerate(pdf_files):
            try:
                count = len(split_notes(p))
            except Exception:
                count = 0
            payload = _json.dumps({"name": p.name, "note_count": count, "index": i, "total": total})
            yield f"event: pdf\ndata: {payload}\n\n"
        yield "event: done\ndata: {}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp_core.route("/api/evaluate/stream")
def api_evaluate_stream():
    """SSE stream: emits check-level events as evaluation progresses."""
    from flask import Response, stream_with_context

    candidate, err = resolve_pdf(request.args.get("pdf", ""))
    if err:
        return err

    inner_judge = current_app.config["INNER_JUDGE"]
    ruleset     = current_app.config["RULESET"]

    return Response(
        stream_with_context(evaluate_pdf_stream(candidate, inner_judge, ruleset=ruleset)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp_core.route("/pdf/<path:name>")
def serve_pdf(name: str):
    source_dir = current_app.config["SOURCE_DIR"]
    candidate = (source_dir / name).resolve()
    if source_dir.resolve() not in candidate.parents:
        abort(403)
    return send_from_directory(str(source_dir.resolve()), name, mimetype="application/pdf")


@bp_core.route("/api/evaluate")
def api_evaluate():
    candidate, err = resolve_pdf(request.args.get("pdf", ""))
    if err:
        return err
    inner_judge = current_app.config["INNER_JUDGE"]
    ruleset     = current_app.config["RULESET"]
    try:
        result = evaluate_pdf(candidate, inner_judge, ruleset=ruleset)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@bp_core.route("/api/rulesets")
def api_rulesets():
    """Return all available rulesets and the currently active one."""
    from compliance.ruleset import list_rulesets
    ruleset = current_app.config["RULESET"]
    return jsonify({
        "active": ruleset.id,
        "rulesets": list_rulesets(),
    })
