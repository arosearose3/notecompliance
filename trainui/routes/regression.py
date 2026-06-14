"""Regression corpus routes: corpus, pin, unpin, run (per-ruleset)."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from compliance.ingest import split_notes
from trainui.corpus import load_corpus, save_corpus
from trainui.evaluation import build_bundles
from trainui.judges import ConfigurableRecordingJudge

bp_regression = Blueprint("regression", __name__)


def _ruleset_id() -> str:
    return current_app.config["RULESET"].id


@bp_regression.route("/api/regression/corpus")
def api_regression_corpus():
    return jsonify(load_corpus(_ruleset_id()))


@bp_regression.route("/api/regression/pin", methods=["POST"])
def api_regression_pin():
    rid    = _ruleset_id()
    body   = request.get_json(force=True)
    corpus = load_corpus(rid)
    corpus = [e for e in corpus if not (
        e["pdf"] == body["pdf"] and
        e["note_index"] == body["note_index"] and
        e["standard_id"] == body["standard_id"]
    )]
    body["pinned_at"]  = datetime.utcnow().isoformat()
    body["ruleset_id"] = rid
    corpus.append(body)
    save_corpus(corpus, rid)
    return jsonify({"ok": True, "total": len(corpus)})


@bp_regression.route("/api/regression/unpin", methods=["POST"])
def api_regression_unpin():
    rid    = _ruleset_id()
    body   = request.get_json(force=True)
    corpus = [e for e in load_corpus(rid) if not (
        e["pdf"] == body["pdf"] and
        e["note_index"] == body["note_index"] and
        e["standard_id"] == body["standard_id"]
    )]
    save_corpus(corpus, rid)
    return jsonify({"ok": True, "total": len(corpus)})


@bp_regression.route("/api/regression/run")
def api_regression_run():
    source_dir  = current_app.config["SOURCE_DIR"]
    inner_judge = current_app.config["INNER_JUDGE"]
    ruleset     = current_app.config["RULESET"]
    corpus      = load_corpus(ruleset.id)
    results     = []
    all_checks  = ruleset.checks()

    for entry in corpus:
        pdf_path = source_dir / entry["pdf"]
        if not pdf_path.is_file():
            results.append({**entry, "actual": "error", "match": False, "error": "PDF not found"})
            continue
        try:
            notes  = split_notes(pdf_path)
            ni     = entry["note_index"]
            if ni >= len(notes):
                results.append({**entry, "actual": "error", "match": False, "error": "Note index OOB"})
                continue
            note   = notes[ni]
            bundle = build_bundles(notes).get(note.header.member_name or "unknown")
            check  = next((c for c in all_checks if c.standard_id == entry["standard_id"]), None)
            if not check:
                results.append({**entry, "actual": "error", "match": False, "error": "Check not registered"})
                continue
            rj     = ConfigurableRecordingJudge(inner_judge, entry["standard_id"])
            result = check.run(note, rj, bundle)
            match  = result.verdict == entry["expected_verdict"]
            results.append({**entry, "actual": result.verdict, "match": match})
        except Exception as exc:
            results.append({**entry, "actual": "error", "match": False, "error": str(exc)})

    total  = len(results)
    passed = sum(1 for r in results if r.get("match"))
    return jsonify({"total": total, "passed": passed, "failed": total - passed, "results": results})
