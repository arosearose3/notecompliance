"""Flask application factory for the standards-evaluation training UI."""

from __future__ import annotations

import sys
from pathlib import Path

from trainui.paths import DEFAULT_OUTPUT_DIR, REPO_ROOT

# Read the HTML template once at module load time.
# Served verbatim (not via Jinja) so stray {{ / {% in user-edited content
# can never cause a template-rendering error.
_INDEX_HTML = (REPO_ROOT / "trainui" / "templates" / "index.html").read_text(encoding="utf-8")


def create_app(source_dir: Path, inner_judge, output_dir: Path | None = None):
    try:
        from flask import Flask, jsonify
    except ImportError:
        sys.exit("Flask is required: pip install flask")

    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["SOURCE_DIR"]  = source_dir
    app.config["OUTPUT_DIR"]  = output_dir
    app.config["INNER_JUDGE"] = inner_judge

    @app.route("/")
    def index():
        return _INDEX_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

    from trainui.routes import register_blueprints
    register_blueprints(app)

    return app
