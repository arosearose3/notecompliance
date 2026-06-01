"""Change-request artifact builders (Tier 3a)."""

from __future__ import annotations

from datetime import datetime

from trainui.data import STANDARD_TITLES
from trainui.paths import CHECKS_DIR, RECORD_STANDARDS_PATH

_MODULE_FOR_PREFIX = {
    "A": "a_identification", "B": "b_entry", "C": "c_medication",
    "D": "d_assessment",     "E": "e_treatment_plan", "F": "f_progress",
    "G": "g_discharge_planning", "H": "h_discharge_summary",
    "I": "i_coordination",  "J": "j_referrals", "K": "k_telehealth",
}


def read_check_source(standard_id: str) -> str:
    prefix = standard_id[0] if standard_id else ""
    module_name = _MODULE_FOR_PREFIX.get(prefix, "")
    if not module_name:
        return "(check source not found)"
    check_file = CHECKS_DIR / f"{module_name}.py"
    if not check_file.is_file():
        return "(check source not found)"
    lines = check_file.read_text(encoding="utf-8").split("\n")
    class_name = f"Check{standard_id}"
    start = next(
        (i for i, l in enumerate(lines) if l.strip().startswith(f"class {class_name}:")),
        None,
    )
    if start is None:
        return check_file.read_text(encoding="utf-8")
    end = next(
        (
            i for i in range(start + 1, len(lines))
            if lines[i].startswith("class ") and not lines[i].startswith(f"class {class_name}")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def build_request_artifact(body: dict, check_source: str) -> str:
    sid   = body.get("standard_id", "")
    title = STANDARD_TITLES.get(sid, sid)
    ts    = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    standards_text = (
        RECORD_STANDARDS_PATH.read_text(encoding="utf-8")
        if RECORD_STANDARDS_PATH.is_file()
        else "(not found)"
    )
    judge_calls = body.get("judge_calls", [])

    md = f"""# Code-Change Request: Standard {sid} — {title}
Generated: {ts}

## The fix requested

**Standard:** {sid} — {title}
**Note type:** {body.get("note_type", "")}
**Current verdict:** `{body.get("current_verdict", "")}`
**Desired verdict:** `{body.get("desired_verdict", "")}`

### Description

{body.get("description", "(none provided)")}

---

## Record Standards reference (full text)

```
{standards_text}
```

---

## Current check source (`compliance/checks/`)

```python
{check_source}
```

---

## Note's structured inputs (non-PHI)

**Sections extracted from note:** `{body.get("section_keys", [])}`
**Sections the check searched for:** `{body.get("sections_searched", [])}`
**Sections not found:** `{body.get("sections_missing", [])}`
**Header fields:** `{body.get("header", {})}`

---

## Judge path (if applicable)
"""
    for i, call in enumerate(judge_calls):
        md += f"""
### Judge call {i + 1}

**Question:** {call.get("effective_question") or call.get("question", "")}

**Context sent (truncated):**
```
{call.get("context", "")[:600]}
```

**Judge verdict:** `{call.get("verdict", "")}` — {call.get("rationale", "")}
"""

    md += f"""
---

## Hard constraints for the implementation

1. Keep the `run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult` signature.
2. Return a `CheckResult` using `passed()`, `failed()`, `not_applicable()`, or `manual_review()` helpers from `compliance.checks.base`.
3. Do not broaden the applicability gate (`if note.note_type not in (...)` guard must remain).
4. Only modify the rule detection logic — do not change the judge question unless explicitly requested.
5. The check must handle the case where the relevant section is absent (return `fail` or `manual_review` appropriately).
6. Commit the change and confirm it via `python -m compliance audit --input sourcedocs/ --output /tmp/test_reports/`.

## Expected outcome

The check for standard **{sid}** should return `{body.get("desired_verdict", "")}` for a {body.get("note_type", "")} note with the inputs described above.
"""
    return md


def build_rewrite_request_artifact(body: dict) -> str:
    """Tier-R3 change-request artifact for a data-driven rewrite action."""
    pdf_name  = body.get("pdf", "")
    note_idx  = int(body.get("note", 0))
    sid       = body.get("standard_id", "")
    desc      = body.get("description", "")
    sel_spans = body.get("spans", [])
    desired   = body.get("desired_replacement", "")
    data_src  = body.get("data_source", "")

    md = f"""# Rewrite-Action Change Request
Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

## What is being requested

**PDF:** {pdf_name}  **Note index:** {note_idx}  **Standard:** {sid}

### Description
{desc}

### Target spans (from fitz get_text("dict"))
"""
    for s in sel_spans:
        md += f"- Page {s.get('page_index')}: `{s.get('old_text', '')}`\n"

    md += f"""
### Desired replacement
{desired}

### Data source the transform should consult
{data_src or "(none — deterministic replacement)"}

---

## Hard constraints for the implementation

1. Register as a class in `compliance/rewrite/actions/` implementing `.locate()` and `.transform()`.
2. The applier (`compliance.rewrite.apply_plan`) handles all fitz writes — actions must NOT call fitz save/redact directly.
3. Never modify originals. Output always goes to `--output` directory.
4. Keep replacements within the original span width where possible (flag overflow otherwise).
5. Register via `compliance/rewrite/actions/__init__.py`.
6. After implementing, test via `trainstandards.py` → card dialog → "Author a rewrite…"

## Standard being remediated

Standard {sid} — {STANDARD_TITLES.get(sid, "")}
"""
    return md
