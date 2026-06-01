"""Rewrite routes: actions, spans, preview, apply, config, generate-request, output PDF serving."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

from compliance import config as cfg
from compliance.ingest import split_notes
from trainui.artifacts import build_rewrite_request_artifact
from trainui.paths import RULE_REQUESTS_DIR
from trainui.webutil import resolve_pdf

bp_rewrite = Blueprint("rewrite", __name__)


@bp_rewrite.route("/api/rewrite/actions")
def api_rewrite_actions():
    """List all registered rewrite actions (built-in + Tier-R1 declarative)."""
    from compliance.rewrite import ACTION_REGISTRY
    from compliance.rewrite import actions as _actions_pkg  # ensure built-ins registered
    from compliance.rewrite.actions.declarative import load_declarative_actions

    result = []
    for action in ACTION_REGISTRY.values():
        result.append({
            "id": action.id,
            "label": action.label,
            "scope": action.scope,
            "params": action.params,
            "applies_to": action.applies_to,
            "tier": "builtin",
        })
    for action in load_declarative_actions():
        result.append({
            "id": action.id,
            "label": action.label,
            "scope": action.scope,
            "params": action.params,
            "applies_to": action.applies_to,
            "tier": "R1",
        })
    return jsonify(result)


@bp_rewrite.route("/api/rewrite/spans")
def api_rewrite_spans():
    """Enumerate selectable text spans for a note via fitz get_text("dict")."""
    try:
        import fitz
    except ImportError:
        return jsonify({"error": "PyMuPDF (fitz) not installed: pip install pymupdf"}), 500

    pdf_name = request.args.get("pdf", "")
    note_idx = int(request.args.get("note", "0"))

    candidate, err = resolve_pdf(pdf_name)
    if err:
        return err

    try:
        notes = split_notes(candidate)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if note_idx >= len(notes):
        return jsonify({"error": "note index out of range"}), 400

    note = notes[note_idx]
    page_indices = note.page_indices

    doc = fitz.open(str(candidate))
    pages_data = []
    for src_idx in page_indices:
        page = doc[src_idx]
        page_spans = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text or len(text) < 3:
                        continue
                    is_header = any(
                        kw in text for kw in
                        ["Clinician:", "Supervisor:", "Date and Time:", "signed this note"]
                    ) or (note.header.clinician and note.header.clinician in text)
                    page_spans.append({
                        "text":       span["text"],
                        "page_index": src_idx,
                        "rect":       list(span["bbox"]),
                        "origin":     list(span["origin"]),
                        "size":       span["size"],
                        "font":       span.get("font", ""),
                        "is_header":  is_header,
                    })
        page_spans.sort(key=lambda s: (0 if s["is_header"] else 1, s["rect"][1]))
        pages_data.append({"page_index": src_idx, "spans": page_spans})
    doc.close()

    return jsonify({
        "pdf":        pdf_name,
        "note_index": note_idx,
        "note_type":  note.note_type,
        "pages":      pages_data,
    })


@bp_rewrite.route("/api/rewrite/preview", methods=["POST"])
def api_rewrite_preview():
    """Build a RewritePlan and return per-span diff + overflow flags. Nothing written."""
    try:
        import fitz
    except ImportError:
        return jsonify({"error": "PyMuPDF (fitz) not installed: pip install pymupdf"}), 500

    body           = request.get_json(force=True)
    pdf_name       = body.get("pdf", "")
    note_idx       = int(body.get("note", 0))
    action_id      = body.get("action_id", "")
    action_params  = body.get("params", {})
    selected_spans = body.get("spans", [])

    candidate, err = resolve_pdf(pdf_name)
    if err:
        return err

    try:
        notes = split_notes(candidate)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    if note_idx >= len(notes):
        return jsonify({"error": "note index out of range"}), 400
    note = notes[note_idx]

    from compliance.rewrite import ACTION_REGISTRY, actions as _ap
    from compliance.rewrite.actions.declarative import load_declarative_actions
    from compliance.rewrite.types import RewritePlan, TargetSpan

    all_actions = dict(ACTION_REGISTRY)
    for da in load_declarative_actions():
        all_actions[da.id] = da

    action = all_actions.get(action_id)
    if not action:
        return jsonify({"error": f"Unknown action: {action_id}"}), 400

    doc  = fitz.open(str(candidate))
    plan = RewritePlan()

    for sel in selected_spans:
        src_idx = sel["page_index"]
        if src_idx not in note.page_indices:
            continue
        page    = doc[src_idx]
        located = action.locate(page, note, action_params)
        for span in located:
            if span.old_text == sel.get("old_text") or (
                abs(span.rect[0] - sel["rect"][0]) < 2 and
                abs(span.rect[1] - sel["rect"][1]) < 2
            ):
                new_text = action.transform(span, note, action_params, None)
                if new_text is not None and new_text != span.old_text:
                    plan.add(span, new_text)
    doc.close()

    overflow_flags = plan.overflow_flags()
    diff = []
    for i, (span, new_text) in enumerate(plan.entries):
        diff.append({
            "page_index": span.page_index,
            "old_text":   span.old_text,
            "new_text":   new_text,
            "rect":       list(span.rect),
            "overflow":   overflow_flags[i] if i < len(overflow_flags) else False,
        })

    return jsonify({
        "pdf":          pdf_name,
        "note_index":   note_idx,
        "action_id":    action_id,
        "diff":         diff,
        "has_overflow": any(overflow_flags),
    })


@bp_rewrite.route("/api/rewrite/apply", methods=["POST"])
def api_rewrite_apply():
    """Apply a RewritePlan: write corrected PDF to output_dir, return manifest."""
    try:
        import fitz  # noqa: F401
    except ImportError:
        return jsonify({"error": "PyMuPDF (fitz) not installed: pip install pymupdf"}), 500

    body          = request.get_json(force=True)
    pdf_name      = body.get("pdf", "")
    note_idx      = int(body.get("note", 0))
    action_id     = body.get("action_id", "")
    diff          = body.get("diff", [])
    overflow_ack  = body.get("overflow_acknowledged", False)
    standard_id   = body.get("standard_id")

    candidate, err = resolve_pdf(pdf_name)
    if err:
        return err

    if any(d.get("overflow") for d in diff) and not overflow_ack:
        return jsonify({
            "error":   "overflow_not_acknowledged",
            "message": "One or more replacements may overflow their span. Set overflow_acknowledged=true to proceed.",
        }), 409

    try:
        notes = split_notes(candidate)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    if note_idx >= len(notes):
        return jsonify({"error": "note index out of range"}), 400
    note = notes[note_idx]

    from compliance.rewrite.applier import apply_plan
    from compliance.rewrite.types import RewritePlan, TargetSpan

    plan = RewritePlan()
    for d in diff:
        plan.add(
            TargetSpan(
                page_index=d["page_index"],
                rect=tuple(d["rect"]),
                origin=tuple(d.get("origin", d["rect"][:2])),
                size=d.get("size", 10.0),
                font=d.get("font", "helv"),
                old_text=d["old_text"],
            ),
            d["new_text"],
        )

    output_dir  = current_app.config["OUTPUT_DIR"]
    output_path = output_dir / pdf_name
    note_meta   = {
        "type":         note.note_type,
        "service_date": str(note.header.service_date) if note.header.service_date else None,
        "page_indices": note.page_indices,
    }

    try:
        result = apply_plan(
            source_pdf=candidate,
            output_pdf=output_path,
            plan=plan,
            pages_to_include=set(note.page_indices),
            action_id=action_id,
            note_meta=note_meta,
            standard_id=standard_id,
            operator="trainstandards",
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "ok":               True,
        "output_pdf":       result.output_pdf.name,
        "spans_changed":    result.spans_changed,
        "manifest":         result.manifest,
        "rewritten_pdf_url": f"/pdf/output/{pdf_name}",
    })


@bp_rewrite.route("/pdf/output/<path:name>")
def serve_output_pdf(name: str):
    """Serve a rewritten PDF from the output directory."""
    output_dir = current_app.config["OUTPUT_DIR"]
    candidate  = (output_dir / name).resolve()
    if output_dir.resolve() not in candidate.parents:
        abort(403)
    return send_from_directory(str(output_dir.resolve()), name, mimetype="application/pdf")


@bp_rewrite.route("/api/rewrite/config", methods=["GET", "POST"])
def api_rewrite_config():
    """Read/write rules/rewrites.yaml (Tier-R1 declarative actions)."""
    path = cfg.RULES_DIR / "rewrites.yaml"
    if request.method == "GET":
        return jsonify(cfg.get_rewrites())
    body = request.get_json(force=True)
    if not isinstance(body, list):
        return jsonify({"error": "expected list"}), 400
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
    cfg.invalidate(path)
    return jsonify({"ok": True, "count": len(body)})


@bp_rewrite.route("/api/rewrite/generate-request", methods=["POST"])
def api_rewrite_generate_request():
    """Emit a Tier-R3 change-request artifact for a data-driven rewrite action."""
    body = request.get_json(force=True)
    ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    sid  = body.get("standard_id", "")
    md   = build_rewrite_request_artifact(body)
    RULE_REQUESTS_DIR.mkdir(exist_ok=True)
    fname = f"rewrite_{sid}_{ts}.md"
    (RULE_REQUESTS_DIR / fname).write_text(md, encoding="utf-8")
    return jsonify({"markdown": md, "file": str(RULE_REQUESTS_DIR / fname)})
