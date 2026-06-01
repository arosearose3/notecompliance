"""
Single source of truth for all repo-root-relative paths.

trainui/ is one level below the repo root, so:
  Path(__file__).resolve().parent  →  .../trainui/
  Path(__file__).resolve().parent.parent  →  .../fixtnpdf/  (repo root)

Every module in trainui/ that needs a repo-root path imports from here.
No other module uses Path(__file__) for repo-relative resolution.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RULES_DIR             = REPO_ROOT / "rules"
CHECKS_DIR            = REPO_ROOT / "compliance" / "checks"
RECORD_STANDARDS_PATH = REPO_ROOT / "Record Standards.txt"
RULE_REQUESTS_DIR     = REPO_ROOT / "rule_requests"
DEFAULT_OUTPUT_DIR    = REPO_ROOT / "output"
CORPUS_PATH           = RULES_DIR / "corpus.json"
