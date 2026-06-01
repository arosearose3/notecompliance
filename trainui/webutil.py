"""Shared path-safety helpers for blueprint routes."""

from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify


def resolve_pdf(name: str):
    """
    Returns (candidate_path, None) on success, or (None, (response, status)) on
    failure, preserving the original 400/403/404 contract.
    """
    if not name:
        return None, (jsonify({"error": "pdf parameter required"}), 400)
    source_dir: Path = current_app.config["SOURCE_DIR"]
    candidate = (source_dir / name).resolve()
    if source_dir.resolve() not in candidate.parents:
        return None, (jsonify({"error": "forbidden"}), 403)
    if not candidate.is_file():
        return None, (jsonify({"error": "not found"}), 404)
    return candidate, None


def resolve_output_pdf(name: str):
    """
    Same as resolve_pdf but resolves against OUTPUT_DIR.
    Returns (candidate_path, None) on success or (None, (response, status)).
    """
    if not name:
        return None, (jsonify({"error": "pdf name required"}), 400)
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    candidate = (output_dir / name).resolve()
    if output_dir.resolve() not in candidate.parents:
        return None, (jsonify({"error": "forbidden"}), 403)
    if not candidate.is_file():
        return None, (jsonify({"error": "not found"}), 404)
    return candidate, None
