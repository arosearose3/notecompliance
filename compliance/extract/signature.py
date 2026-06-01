"""Extract clinician signature block from the last page of a note."""

from __future__ import annotations

import re

RE_SIGNATURE = re.compile(
    r"([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)+)"   # name
    r",\s+(\S+)"                                          # credential
    r",\s+([^,\n]+)"                                      # degree title
    r",?\s+License\s+([A-Z]{2})\s+(\d+)"                 # license
    r"[^.]*signed this note",
    re.IGNORECASE,
)

RE_SIMPLE_SIGNATURE = re.compile(
    r"([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)+)"
    r",\s+(\S+)"
    r".*?signed this note",
    re.IGNORECASE | re.DOTALL,
)


def extract_signature(text: str) -> dict | None:
    """
    Return a dict with keys: name, credential, degree, license_state, license_id.
    Returns None if no signature block is found.
    """
    m = RE_SIGNATURE.search(text)
    if m:
        return {
            "name":          m.group(1).strip(),
            "credential":    m.group(2).strip(),
            "degree":        m.group(3).strip(),
            "license_state": m.group(4),
            "license_id":    m.group(5),
        }

    # Fallback: simpler pattern, fewer fields
    m = RE_SIMPLE_SIGNATURE.search(text)
    if m:
        return {
            "name":          m.group(1).strip(),
            "credential":    m.group(2).strip(),
            "degree":        None,
            "license_state": None,
            "license_id":    None,
        }

    return None
