"""
compliance — clinical record compliance audit engine.

Entry point:  python -m compliance audit --input <dir> --output <dir>
"""

from compliance.ingest import split_notes
from compliance.runner import run_batch

__all__ = ["split_notes", "run_batch"]
