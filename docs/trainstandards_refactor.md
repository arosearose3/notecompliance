# Plan — Refactor `trainstandards.py` into smaller components

**Status:** implementation plan. No code in this change. Written to be
implemented directly (target implementer: Sonnet).
**Audience:** the engineer splitting the 3,053-line `trainstandards.py`.

---

## 1. BLUF

`trainstandards.py` is **3,053 lines / 131 KB** in one file. Nearly half of it
(~1,438 lines) is a single embedded `_HTML` raw string; another ~627 lines is
one `create_app()` function holding ~30 Flask routes as closures.

This refactor splits it into a **`trainui/` package** plus a **thin
`trainstandards.py` launcher** that preserves the exact CLI invocation
(`python trainstandards.py --input … --output … --judge …`). It is a **pure
move**: no behavior changes, no new features. The risk is almost entirely in
two places — the embedded web assets and one path assumption — and §4 and §5
address both head-on.

**The single most important correctness item is §4 (the `Path(__file__)`
trap).** Read it before moving any Python.

---

## 2. Current structure (line map of `trainstandards.py`)

| Lines | Section | Kind |
|---|---|---|
| 1–46 | Module docstring + imports | imports |
| 48–62 | `class SkipJudge` | judge wrapper |
| 64–114 | `ALL_CHECKS` (49 check instances) | data |
| 116 | `RULES_DIR = Path(__file__).parent / "rules"` | **path (see §4)** |
| 120–171 | `STANDARD_TITLES` (47 entries) | data |
| 172 | `STANDARD_ORDER` | data |
| 178–188 | `REWRITABLE_STANDARDS` | data |
| 190–399 | `STANDARD_TEXT` (verbatim payer text, ~210 lines) | data |
| 400–437 | `SECTIONS_FOR_STANDARD` | data |
| 440–466 | `class ConfigurableRecordingJudge` | judge wrapper |
| 470–478 | `_build_bundles(notes)` | evaluation |
| 480–640 | `evaluate_pdf_stream(...)` (SSE generator) | evaluation |
| 642–757 | `evaluate_pdf(...)` | evaluation |
| 760–776 | `_corpus_path` / `_load_corpus` / `_save_corpus` | corpus |
| 787–806 | `_read_check_source(standard_id)` | artifacts (**path, §4**) |
| 809–892 | `_build_request_artifact(body, src)` | artifacts (**path, §4**) |
| 895–915 | `_effective_synonyms` / `_effective_matrix` | config helpers |
| 918–2356 | `_HTML = r"""…"""` | **web assets (§5)** |
| 2359–2984 | `create_app(source_dir, inner_judge, output_dir)` (~30 routes) | Flask (§6) |
| 2987–end | `main()` (argparse, judge selection, `app.run`) | CLI |

Inside `_HTML` (relative line numbers within the string):

| Rel. lines | Block | Size |
|---|---|---|
| 1–5 | `<!DOCTYPE>`, `<head>` open | — |
| 6–273 | `<style> … </style>` | **267 lines CSS** |
| 274–274 | `</head>` | — |
| 275–371 | `<body>` structure (panes, modals, overlays) | **~97 lines HTML** |
| 372–1434 | `<script> … </script>` | **~1,062 lines JS** |
| 1435–1438 | `</body></html>` | — |

**Confirmed facts that make this safe:**
- `_HTML` is a `r"""…"""` raw string served verbatim at the `/` route. There is
  **no `.format()`, f-string, or Jinja interpolation** — it is fully static.
- The `<script>` block is already at the end of `<body>`, and its last
  statement is `init();`. DOM-ready timing is preserved as long as the
  extracted JS stays at the end of `<body>` (§5).
- **No other Python module imports `trainstandards`** (verified). The only
  external reference is a comment in `compliance/judges/ollama.py`. So the
  module's public names can move freely.

---

## 3. Target structure

A package `trainui/` sibling to `compliance/`. `trainstandards.py` becomes a
~6-line launcher so the existing command line is unchanged. (A package cannot
share the name of an existing `.py` file in the same directory — hence
`trainui/`, not `trainstandards/`.)

```
trainstandards.py            # thin launcher — see §7
trainui/
  __init__.py
  paths.py                   # REPO_ROOT + all repo-root-relative paths (§4)
  data.py                    # ALL_CHECKS, STANDARD_TITLES, STANDARD_ORDER,
                             #   REWRITABLE_STANDARDS, SECTIONS_FOR_STANDARD, STANDARD_TEXT
  judges.py                  # SkipJudge, ConfigurableRecordingJudge
  evaluation.py              # _build_bundles, evaluate_pdf, evaluate_pdf_stream
  corpus.py                  # _corpus_path, _load_corpus, _save_corpus
  artifacts.py               # _read_check_source, _build_request_artifact,
                             #   build_rewrite_request (moved from the rewrite route)
  config_helpers.py          # _effective_synonyms, _effective_matrix
  webutil.py                 # safe_pdf_path() + safe_output_path() shared helpers (§6)
  app.py                     # create_app(): Flask app, config, index route, blueprint registration
  cli.py                     # main(): argparse, judge selection, app.run
  routes/
    __init__.py              # register_blueprints(app)
    core.py                  # /api/pdfs[/stream], /api/evaluate[/stream], /pdf/<name>
    config.py                # /api/config/{synonyms,applicability,thresholds}
    prompts.py               # /api/prompts/<id>[, /save, /delete, /test]
    regression.py            # /api/regression/{corpus,pin,unpin,run}
    rewrite.py               # /api/rewrite/{actions,spans,preview,apply,config,generate-request}, /pdf/output/<name>
    misc.py                  # /api/generate-request, /api/reload
  templates/
    index.html               # the <body> region of _HTML (with <link>/<script src> wiring)
  static/
    css/styles.css           # the <style> body
    js/app.js                # the <script> body (single file in v1 — see §5 and §9)
```

After the split, no module should exceed ~400 lines except `data.py` (pure data,
~370) and `app.js` (the JS, ~1,062 — left whole in v1 on purpose; §9 covers
splitting it later).

---

## 4. The `Path(__file__)` trap — do this FIRST

Today `trainstandards.py` is at the repo root, so `Path(__file__).parent` **is**
the repo root, and every repo-root-relative path works by accident. The moment
this code moves into `trainui/…`, `Path(__file__).parent` becomes `…/trainui/`
and **every one of these paths breaks at runtime** (no import error — a wrong
directory, silently).

Create `trainui/paths.py` as the single source of truth:

```python
from pathlib import Path

# trainui/ is one level below repo root: paths.py → trainui/ → repo root
REPO_ROOT = Path(__file__).resolve().parent.parent

RULES_DIR             = REPO_ROOT / "rules"
CHECKS_DIR            = REPO_ROOT / "compliance" / "checks"
RECORD_STANDARDS_PATH = REPO_ROOT / "Record Standards.txt"
RULE_REQUESTS_DIR     = REPO_ROOT / "rule_requests"
DEFAULT_OUTPUT_DIR    = REPO_ROOT / "output"
CORPUS_PATH           = RULES_DIR / "corpus.json"
```

Then rewrite **all six** `Path(__file__)` sites (grep-verified) to import from
`paths`:

| Original line | Original expression | Replace with |
|---|---|---|
| 116 | `RULES_DIR = Path(__file__).parent / "rules"` | `from trainui.paths import RULES_DIR` |
| 792 (`_read_check_source`) | `Path(__file__).parent / "compliance" / "checks" / …` | `CHECKS_DIR / f"{module_name}.py"` |
| 813 (`_build_request_artifact`) | `Path(__file__).parent / "Record Standards.txt"` | `RECORD_STANDARDS_PATH` |
| 2368 (`create_app`) | `output_dir or (Path(__file__).parent / "output")` | `output_dir or DEFAULT_OUTPUT_DIR` |
| 2608 (`/api/generate-request`) | `Path(__file__).parent / "rule_requests"` | `RULE_REQUESTS_DIR` |
| 2976 (`/api/rewrite/generate-request`) | `Path(__file__).parent / "rule_requests"` | `RULE_REQUESTS_DIR` |

`_corpus_path()` uses `RULES_DIR` and needs no change once `RULES_DIR` comes
from `paths` (or point it at `CORPUS_PATH` directly).

**Verification for this step alone:** after wiring `paths.py`, add a temporary
`assert RULES_DIR.is_dir()` and print `RECORD_STANDARDS_PATH.is_file()` at
startup; both must be true. Remove once confirmed.

---

## 5. Extract the web assets (`_HTML` → static files)

This removes ~1,438 lines and is the biggest single win. Split the one raw
string into three files by its existing block boundaries (§2 table).

### 5.1 Files

- **`trainui/static/css/styles.css`** ← the bytes **between** `<style>` and
  `</style>` (rel. lines 7–272), verbatim. No `<style>` tags in the file.
- **`trainui/static/js/app.js`** ← the bytes **between** `<script>` and
  `</script>` (rel. lines 373–1433), verbatim. No `<script>` tags. Keep the
  trailing `init();` as the last line.
- **`trainui/templates/index.html`** ← everything else: the `<!DOCTYPE>`,
  `<head>`, `<body>` structure, with two edits:
  - In `<head>`, replace the entire `<style>…</style>` block with
    `<link rel="stylesheet" href="/static/css/styles.css">`.
  - Just before `</body>`, replace the entire `<script>…</script>` block with
    `<script src="/static/js/app.js"></script>`.

### 5.2 Hard constraints (these are the failure modes)

1. **`app.js` must be a classic script, not `type="module"`.** The UI wires
   handlers as inline `onclick="rwApply()"`, `onclick="openModal(...)"`, etc.,
   which resolve against **global** functions. ES modules scope functions
   privately and would break every inline handler. Use a plain
   `<script src=…>` so all functions stay global.
2. **`app.js` loads at the end of `<body>`** (where the original `<script>`
   already sat). It calls `init()` immediately, which touches the DOM via
   `getElementById`. If placed in `<head>` without `defer`, `init()` runs before
   the DOM exists and the page breaks. End-of-body placement preserves today's
   timing exactly.
3. **Do not serve `index.html` through Jinja.** Although the body is currently
   brace-free, serving via `render_template` would make any future `{{`/`{%`
   typed into the HTML explode. Mirror today's behavior — serve static bytes:

   ```python
   # app.py
   from trainui.paths import REPO_ROOT
   _INDEX_HTML = (REPO_ROOT / "trainui" / "templates" / "index.html").read_text(encoding="utf-8")

   @app.route("/")
   def index():
       return _INDEX_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}
   ```

4. **Flask static resolution.** With `app = Flask(__name__)` and `__name__ ==
   "trainui.app"`, Flask serves `trainui/static/` at `/static/` automatically —
   so `/static/css/styles.css` and `/static/js/app.js` resolve with no extra
   config. If in doubt, pass it explicitly:
   `Flask(__name__, static_folder=str(REPO_ROOT / "trainui" / "static"))`.

### 5.3 Asset regression gate

The old "byte-identical served HTML" check is **invalid** once `<style>` becomes
`<link>` — don't use it. Instead, two checks:

- **Content equality:** `styles.css` must equal the original `<style>` inner
  text byte-for-byte; `app.js` must equal the original `<script>` inner text
  byte-for-byte. (Extract by slicing the original `_HTML` on the tag boundaries
  and `assert` equality during migration, then delete the assert.)
- **Functional smoke test:** §8.

---

## 6. Move the Flask routes into blueprints

`create_app` currently defines ~30 routes as **closures** over `source_dir`,
`inner_judge`, and `_output_dir`. Blueprints in separate files can't see those
locals, so move them onto `app.config` and read them via `current_app`.

### 6.1 In `create_app` (`app.py`)

```python
def create_app(source_dir, inner_judge, output_dir=None):
    from flask import Flask
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["SOURCE_DIR"]  = source_dir
    app.config["OUTPUT_DIR"]  = output_dir or DEFAULT_OUTPUT_DIR
    app.config["INNER_JUDGE"] = inner_judge
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)

    # index route here (§5.2)
    from trainui.routes import register_blueprints
    register_blueprints(app)
    return app
```

### 6.2 Shared path-safety helper (`webutil.py`)

The resolve-and-check-parents guard is copy-pasted into ~8 routes. Extract once.
**To keep this a pure move, the helper must preserve the original three distinct
responses** — `400` (missing param), `403` (path escape), `404` (file missing) —
not collapse them into one. Return a `(path, error_response)` pair so each route
keeps today's exact status codes:

```python
from flask import current_app, jsonify

def resolve_pdf(name: str):
    """
    Returns (candidate_path, None) on success, or (None, (json, status)) on
    failure, preserving the original 400/403/404 contract.
    """
    if not name:
        return None, (jsonify({"error": "pdf parameter required"}), 400)
    source_dir = current_app.config["SOURCE_DIR"]
    candidate = (source_dir / name).resolve()
    if source_dir.resolve() not in candidate.parents:
        return None, (jsonify({"error": "forbidden"}), 403)
    if not candidate.is_file():
        return None, (jsonify({"error": "not found"}), 404)
    return candidate, None

def resolve_output_pdf(name: str):
    """Same, against OUTPUT_DIR — used by /pdf/output/<name> (abort(403) form)."""
    ...
```

(If, on reflection, collapsing 400/403/404 into a single 404 is acceptable for
this internal tool, that is allowed — but it is a deliberate behavior change and
must be stated as such, not introduced silently. Default to preserving the
contract above.)

### 6.3 Worked closure → blueprint transformation

This is the per-route edit, repeated ~30 times. Example (`/api/evaluate`):

**Before** (inside `create_app`):
```python
@app.route("/api/evaluate")
def api_evaluate():
    name = request.args.get("pdf", "")
    if not name:
        return jsonify({"error": "pdf parameter required"}), 400
    candidate = (source_dir / name).resolve()
    if source_dir.resolve() not in candidate.parents:
        return jsonify({"error": "forbidden"}), 403
    if not candidate.is_file():
        return jsonify({"error": "not found"}), 404
    result = evaluate_pdf(candidate, inner_judge)
    return jsonify(result)
```

**After** (in `routes/core.py`):
```python
from flask import Blueprint, current_app, request, jsonify
from trainui.evaluation import evaluate_pdf
from trainui.webutil import resolve_pdf

bp_core = Blueprint("core", __name__)

@bp_core.route("/api/evaluate")
def api_evaluate():
    candidate, err = resolve_pdf(request.args.get("pdf", ""))
    if err:
        return err
    result = evaluate_pdf(candidate, current_app.config["INNER_JUDGE"])
    return jsonify(result)
```

Rules for every route move:
- `source_dir` → `current_app.config["SOURCE_DIR"]` (or via `resolve_pdf`).
- `inner_judge` → `current_app.config["INNER_JUDGE"]`.
- `_output_dir` → `current_app.config["OUTPUT_DIR"]`.
- Module-level helpers (`evaluate_pdf`, `_load_corpus`, `_build_request_artifact`,
  …) become explicit imports from the new modules.
- **SSE routes** (`/api/pdfs/stream`, `/api/evaluate/stream`) keep their
  `Response(stream_with_context(...), mimetype="text/event-stream", …)` shape.
  **Read config into locals in the route body *before* building the generator**,
  then close over those locals — e.g. `source_dir = current_app.config["SOURCE_DIR"]`
  on the line above `def generate(): …`. This is exactly what `/api/evaluate/stream`
  already does for `candidate`/`inner_judge`. (Reading `current_app` inside the
  generator also works under `stream_with_context`, but binding to a local first
  is the clean, behavior-preserving form.)

### 6.4 Blueprint registry (`routes/__init__.py`)

```python
def register_blueprints(app):
    from trainui.routes.core import bp_core
    from trainui.routes.config import bp_config
    from trainui.routes.prompts import bp_prompts
    from trainui.routes.regression import bp_regression
    from trainui.routes.rewrite import bp_rewrite
    from trainui.routes.misc import bp_misc
    for bp in (bp_core, bp_config, bp_prompts, bp_regression, bp_rewrite, bp_misc):
        app.register_blueprint(bp)
```

### 6.5 Route → blueprint assignment

| Blueprint (file) | Routes |
|---|---|
| `core.py` | `/api/pdfs`, `/api/pdfs/stream`, `/api/evaluate`, `/api/evaluate/stream`, `/pdf/<path:name>` |
| `config.py` | `/api/config/synonyms`, `/api/config/applicability`, `/api/config/thresholds` |
| `prompts.py` | `/api/prompts/<id>`, `…/save`, `…/delete`, `…/test` |
| `regression.py` | `/api/regression/corpus`, `…/pin`, `…/unpin`, `…/run` |
| `rewrite.py` | `/api/rewrite/actions`, `…/spans`, `…/preview`, `…/apply`, `…/config`, `…/generate-request`, `/pdf/output/<path:name>` |
| `misc.py` | `/api/generate-request`, `/api/reload` |

The `/` index route stays in `app.py` (it's tied to the static-HTML loading),
**not** in a blueprint.

---

## 7. The thin launcher (`trainstandards.py`)

After moving `main()` into `trainui/cli.py`, the root file becomes:

```python
#!/usr/bin/env python3
"""Launcher for the standards-training web UI. See trainui/ for the implementation."""
from trainui.cli import main

if __name__ == "__main__":
    main()
```

`trainui/cli.py` holds the current `main()` verbatim except: the judge-selection
block and `argparse` stay; the final lines call `create_app(source_dir, inner,
output_dir)` from `trainui.app`. The CLI surface (`--input`, `--output`,
`--port`, `--host`, `--judge`, `--ollama-model`, `--ollama-url`, `--no-ai`) is
**unchanged**.

---

## 8. Migration order (do it in this sequence)

Each step leaves the app runnable, so regressions are caught early.

1. **`paths.py` + fix the six path sites (§4)** — still inside the monolith
   first if you like, but easiest to do as the modules are carved out. Verify
   `RULES_DIR`/`RECORD_STANDARDS_PATH` resolve.
2. **`data.py`** — move the five data tables + `ALL_CHECKS`. Pure cut/paste +
   imports. Import them back into `trainstandards.py` so it still runs.
3. **`judges.py`**, **`corpus.py`**, **`config_helpers.py`**, **`artifacts.py`**,
   **`evaluation.py`** — move in this order (evaluation depends on data + judges).
   After each, `python trainstandards.py --input sourcedocs --no-ai` must start.
4. **Web assets (§5)** — extract `styles.css`, `app.js`, `index.html`; switch the
   `/` route to serve the file. Load the page; confirm it renders and evaluates.
5. **Routes → blueprints (§6)** — move one blueprint at a time; after each,
   exercise its endpoints. Do `core` first (it's the critical path), `rewrite`
   last (most endpoints).
6. **`app.py` + `cli.py`**, then reduce `trainstandards.py` to the launcher (§7).
7. Delete now-dead code from the original file (it should be empty but for the
   launcher).

---

## 9. Out of scope / explicitly later

- **Splitting `app.js` into modules.** Tempting (state.js, eval.js, dialog.js,
  editors.js, rewrite.js), but every split adds script-load-order risk because
  the functions share one global scope and reference each other freely. v1
  keeps **one `app.js`**. When split later: classic `<script src>` tags in
  dependency order (state → utils → eval/render → dialog → editors → rewrite),
  all before `</body>`, with `init()` last. Do **not** convert to ES modules
  without first rewriting every inline `onclick=` to `addEventListener`.
- **Splitting `STANDARD_TEXT` out of `data.py`** into `data_payer_text.py` — fine
  to do for readability, but optional; it's inert data.
- **Jinja templating / a build step** — deliberately avoided; the assets stay
  static and hand-served, matching the repo's no-build ethos.
- **Behavior changes** of any kind. This refactor must be a pure move.

---

## 10. Verification (definition of done)

1. `python trainstandards.py --input sourcedocs --no-ai` starts and prints the
   `Source/Output/Rules/Judge` banner (same as today).
2. Browser at `/` renders the three-pane UI; CSS applied; no console errors.
3. `/api/pdfs` lists the source PDFs; clicking one streams evaluation and
   renders cards.
4. Open a card dialog; the synonym / applicability / prompt editors open; a
   regression pin/run works.
5. On a failing rewritable card (e.g. F6/F7), "Author a rewrite…" opens the
   panel, `/api/rewrite/spans` populates, and a preview returns a diff.
6. **Asset content equality** (§5.3): `styles.css` and `app.js` are byte-exact
   copies of the original inline blocks.
7. `grep -rn "Path(__file__)" trainui/` shows the expression **only** in
   `paths.py`.
8. `grep -rn "import trainstandards" --include="*.py" .` still returns nothing
   (the launcher is the only entry point; nothing imports the old module).
```
