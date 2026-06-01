"""
trainstandards.py — Standards-evaluation training UI.

Three-pane Flask web app with interactive rule editing:
  Left   — PDF list from the source directory
  Center — Native browser PDF viewer (iframe)
  Right  — All 47 compliance standard cards (accordion per note)

Card dialog adds:
  • Synonym editor (Tier 1) — add/edit section synonyms live
  • Applicability editor (Tier 1) — change R/C/N-A per doc-type
  • Prompt editor (Tier 2) — edit + test judge questions
  • Pin to corpus / Run regression — regression safeguard
  • Generate change request (Tier 3a) — handoff artifact for Claude Code

Usage:
  python trainstandards.py [--input sourcedocs/] [--port 5000] [--judge null|claude]
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

# ── Compliance package imports ─────────────────────────────────────────────────

from compliance import applicability
from compliance.applicability import applies, get_applicable_standards
from compliance.checks.base import not_applicable as make_not_applicable
from compliance.checks import (
    a_identification, b_entry, c_medication, d_assessment,
    e_treatment_plan, f_progress, g_discharge_planning,
    h_discharge_summary, i_coordination, j_referrals, k_telehealth,
)
from compliance.ingest import split_notes
from compliance.judges.base import JudgeAnswer
from compliance.judges.null import NullJudge
from compliance.models import ContextBundle
from compliance import config as cfg

ALL_CHECKS = [
    a_identification.CheckA1(),
    a_identification.CheckA2(),
    a_identification.CheckA3(),
    a_identification.CheckA4(),
    a_identification.CheckA5(),
    b_entry.CheckB1(),
    b_entry.CheckB2(),
    c_medication.CheckC1(),
    c_medication.CheckC2a(),
    c_medication.CheckC2b(),
    c_medication.CheckC2c(),
    c_medication.CheckC2d(),
    c_medication.CheckC2e(),
    d_assessment.CheckD1(),
    d_assessment.CheckD2(),
    d_assessment.CheckD3(),
    d_assessment.CheckD4(),
    d_assessment.CheckD5(),
    d_assessment.CheckD6(),
    d_assessment.CheckD7(),
    d_assessment.CheckD8(),
    d_assessment.CheckD9(),
    e_treatment_plan.CheckE1(),
    e_treatment_plan.CheckE2(),
    e_treatment_plan.CheckE3(),
    e_treatment_plan.CheckE4(),
    e_treatment_plan.CheckE5(),
    e_treatment_plan.CheckE6(),
    e_treatment_plan.CheckE7(),
    e_treatment_plan.CheckE8(),
    e_treatment_plan.CheckE9(),
    e_treatment_plan.CheckE10(),
    f_progress.CheckF1(),
    f_progress.CheckF2(),
    f_progress.CheckF3(),
    f_progress.CheckF4(),
    f_progress.CheckF5(),
    f_progress.CheckF6(),
    f_progress.CheckF7(),
    f_progress.CheckF8(),
    g_discharge_planning.CheckG1(),
    h_discharge_summary.CheckH1(),
    h_discharge_summary.CheckH2(),
    h_discharge_summary.CheckH3(),
    i_coordination.CheckI1(),
    i_coordination.CheckI2(),
    j_referrals.CheckJ1(),
    k_telehealth.CheckK1(),
    k_telehealth.CheckK2(),
]

RULES_DIR = Path(__file__).parent / "rules"

# ── Standard titles ────────────────────────────────────────────────────────────

STANDARD_TITLES: dict[str, str] = {
    "A1":  "Member ID on each page",
    "A2":  "Demographics, contacts, consent",
    "A3":  "Encounter metadata (date, duration, clinician, diagnosis, service code)",
    "A4":  "Group session — subject covered",
    "A5":  "Family session — attendees and relationships",
    "B1":  "Late entry notation",
    "B2":  "Modification audit trail",
    "C1":  "Allergies and medical conditions",
    "C2a": "Medication order types (standing/PRN/STAT)",
    "C2b": "Medication date, dose, and frequency",
    "C2c": "Medication informed consent",
    "C2d": "Medication change/no-change rationale",
    "C2e": "Discharge medication list with doses",
    "D1":  "Presenting problem, MSE, psychosocial, source",
    "D2":  "Special status assessment (SI/HI/SIB/elopement/harm)",
    "D3":  "Medical and psychiatric history",
    "D4":  "Abuse and trauma history",
    "D5":  "Adolescent sexual behavior history (ages 12–17)",
    "D6":  "Child/adolescent developmental history",
    "D7":  "Substance use history (age 12+)",
    "D8":  "DSM diagnosis consistent with assessment",
    "D9":  "Functional impairment documentation",
    "E1":  "Symptoms/problems tied to diagnosis",
    "E2":  "Problem prioritization; deferred items labelled",
    "E3":  "Level of care rationale linked to impairment",
    "E4":  "Member involvement in treatment planning",
    "E5":  "SMART goals (specific, behavioral, measurable, realistic)",
    "E6":  "Goal time frames",
    "E7":  "Progress toward goals",
    "E8":  "Rationale for estimated treatment length",
    "E9":  "Goal updates on revision",
    "E10": "Re-evaluation when progress stalls",
    "F1":  "Clinician signature",
    "F2":  "Date of service",
    "F3":  "Telehealth documentation",
    "F4":  "Member strengths and limitations toward goals",
    "F5":  "Interventions consistent with treatment-plan goals",
    "F6":  "Follow-up dates",
    "F7":  "Missed appointment outreach documented",
    "F8":  "Time-based duration (start/stop or total)",
    "G1":  "Ongoing discharge planning (criteria, barriers, support)",
    "H1":  "Reason for treatment episode",
    "H2":  "Goals achieved or reasons not achieved",
    "H3":  "Specific aftercare plan",
    "I1":  "Coordination of care (or documented refusal)",
    "I2":  "Coordination at key milestones",
    "J1":  "Referrals to clinicians, services, community resources",
    "K1":  "Telehealth noted in record",
    "K2":  "State-specific telehealth requirements",
}

STANDARD_ORDER = list(STANDARD_TITLES.keys())

# Canonical sections each check looks up (for the synonym editor hint).
SECTIONS_FOR_STANDARD: dict[str, list[str]] = {
    "A2":  ["address", "phone", "emergency_contact", "marital_status", "consent"],
    "C1":  ["allergies", "medical_history"],
    "C2a": ["medications"],
    "C2b": ["medications"],
    "C2c": ["medications"],
    "C2d": ["medications"],
    "C2e": ["medications_at_discharge", "medications"],
    "D1":  ["presenting_problem", "mse", "psychosocial_history"],
    "D3":  ["psychiatric_history", "medical_history"],
    "D4":  ["abuse_history"],
    "D5":  ["sexual_history"],
    "D6":  ["developmental_history"],
    "D7":  ["substance_use"],
    "D8":  ["diagnosis"],
    "D9":  ["functional_impairment"],
    "E1":  ["problems"],
    "E2":  ["problems"],
    "E3":  ["level_of_care"],
    "E4":  ["member_involvement"],
    "E5":  ["goals"],
    "E6":  ["goals"],
    "E7":  ["goals"],
    "E8":  ["treatment_length"],
    "E9":  ["goals"],
    "F4":  ["strengths", "limitations"],
    "F5":  ["interventions"],
    "F6":  ["follow_up"],
    "G1":  ["discharge_plan", "support_systems", "barriers"],
    "H1":  ["reason_for_episode"],
    "H2":  ["goals_achieved"],
    "H3":  ["aftercare"],
    "I1":  ["coordination"],
    "I2":  ["coordination"],
    "J1":  ["referrals"],
}


# ── ConfigurableRecordingJudge ─────────────────────────────────────────────────

class ConfigurableRecordingJudge:
    """
    Wraps any Judge, substitutes per-standard prompt overrides from
    rules/prompts/<id>.md at call time, and records every evaluate() call.
    """

    def __init__(self, inner: object, standard_id: str) -> None:
        self._inner = inner
        self._sid = standard_id
        self.name: str = f"recording({getattr(inner, 'name', '?')})"
        self.calls: list[dict] = []

    def evaluate(self, *, question: str, context: str, hint: str = "") -> JudgeAnswer:
        override = cfg.get_prompt(self._sid)
        effective_q = override if override else question
        answer = self._inner.evaluate(question=effective_q, context=context, hint=hint)
        self.calls.append({
            "question":          question,          # original from code
            "effective_question": effective_q,       # may differ if override active
            "prompt_overridden": override is not None,
            "context":           context[:800],
            "verdict":           answer.verdict,
            "rationale":         answer.rationale,
            "excerpts":          answer.excerpts,
        })
        return answer


# ── Per-PDF evaluation ─────────────────────────────────────────────────────────

def _build_bundles(notes):
    bundles: dict[str, ContextBundle] = {}
    for note in notes:
        name = note.header.member_name or "unknown"
        if name not in bundles:
            bundles[name] = ContextBundle(member_name=name, notes=[])
        bundles[name].notes.append(note)
    return bundles


def evaluate_pdf(pdf_path: Path, inner_judge, *, note_index: int | None = None) -> list[dict]:
    """
    Run all checks against every note in pdf_path (or only note_index if given).
    Returns a list of per-note dicts for JSON.
    """
    notes = split_notes(pdf_path)
    bundles = _build_bundles(notes)
    note_results = []

    target_indices = [note_index] if note_index is not None else range(len(notes))

    for ni in target_indices:
        if ni >= len(notes):
            continue
        note = notes[ni]
        bundle = bundles.get(note.header.member_name or "unknown")
        applicable_ids = set(get_applicable_standards(note.note_type))

        evaluated: dict[str, tuple] = {}
        for check in ALL_CHECKS:
            sid = check.standard_id
            if sid not in applicable_ids:
                continue
            rj = ConfigurableRecordingJudge(inner_judge, sid)
            try:
                result = check.run(note, rj, bundle)
            except Exception as exc:
                result = make_not_applicable(sid, f"Check error: {exc}")
            evaluated[sid] = (result, rj.calls)

        cards = []
        for sid in STANDARD_ORDER:
            title = STANDARD_TITLES[sid]
            appl  = applies(sid, note.note_type)
            sections_searched = SECTIONS_FOR_STANDARD.get(sid, [])
            sections_missing  = [s for s in sections_searched if not note.sections.get(s, "").strip()]

            if appl is None:
                cards.append({
                    "standard_id":      sid,
                    "title":            title,
                    "applicability":    None,
                    "verdict":          "not_applicable",
                    "rationale":        f"Not applicable to {note.note_type} notes.",
                    "excerpts":         [],
                    "page_numbers":     [],
                    "judge_used":       None,
                    "judge_calls":      [],
                    "sections_searched": sections_searched,
                    "sections_missing": sections_missing,
                    "has_prompt_file":  (RULES_DIR / "prompts" / f"{sid}.md").is_file(),
                })
            elif sid in evaluated:
                result, calls = evaluated[sid]
                cards.append({
                    "standard_id":      sid,
                    "title":            title,
                    "applicability":    appl,
                    "verdict":          result.verdict,
                    "rationale":        result.rationale,
                    "excerpts":         list(result.excerpts),
                    "page_numbers":     [p + 1 for p in result.page_numbers],
                    "judge_used":       result.judge_used,
                    "judge_calls":      calls,
                    "sections_searched": sections_searched,
                    "sections_missing": sections_missing,
                    "has_prompt_file":  (RULES_DIR / "prompts" / f"{sid}.md").is_file(),
                })
            else:
                cards.append({
                    "standard_id":      sid,
                    "title":            title,
                    "applicability":    appl,
                    "verdict":          "not_applicable",
                    "rationale":        "Check not registered.",
                    "excerpts":         [],
                    "page_numbers":     [],
                    "judge_used":       None,
                    "judge_calls":      [],
                    "sections_searched": sections_searched,
                    "sections_missing": sections_missing,
                    "has_prompt_file":  False,
                })

        h = note.header
        header_snapshot = {k: v for k, v in {
            "service_date":         str(h.service_date) if h.service_date else None,
            "entry_date":           str(h.entry_date) if h.entry_date else None,
            "duration_minutes":     h.duration_minutes,
            "clinician":            h.clinician,
            "clinician_credential": h.clinician_credential,
            "license_id":           h.license_id,
            "member_name":          h.member_name,
            "member_dob":           str(h.member_dob) if h.member_dob else None,
            "location":             h.location,
            "service_code":         h.service_code,
            "participants":         h.participants,
        }.items() if v is not None}

        note_results.append({
            "note_index":  ni,
            "note_type":   note.note_type,
            "service_date": str(h.service_date) if h.service_date else None,
            "member":      h.member_name or "Unknown",
            "clinician":   h.clinician or "Unknown",
            "page_indices": note.page_indices,
            "first_page":  (note.page_indices[0] + 1) if note.page_indices else 1,
            "section_keys": sorted(note.sections.keys()),
            "header":      header_snapshot,
            "cards":       cards,
        })

    return note_results


# ── Corpus helpers ─────────────────────────────────────────────────────────────

def _corpus_path() -> Path:
    return RULES_DIR / "corpus.json"


def _load_corpus() -> list:
    p = _corpus_path()
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _save_corpus(corpus: list) -> None:
    p = _corpus_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(corpus, indent=2), encoding="utf-8")


# ── Check source reader ────────────────────────────────────────────────────────

_MODULE_FOR_PREFIX = {
    "A": "a_identification", "B": "b_entry", "C": "c_medication",
    "D": "d_assessment",     "E": "e_treatment_plan", "F": "f_progress",
    "G": "g_discharge_planning", "H": "h_discharge_summary",
    "I": "i_coordination",  "J": "j_referrals", "K": "k_telehealth",
}


def _read_check_source(standard_id: str) -> str:
    prefix = standard_id[0] if standard_id else ""
    module_name = _MODULE_FOR_PREFIX.get(prefix, "")
    if not module_name:
        return "(check source not found)"
    check_file = Path(__file__).parent / "compliance" / "checks" / f"{module_name}.py"
    if not check_file.is_file():
        return "(check source not found)"
    lines = check_file.read_text(encoding="utf-8").split("\n")
    class_name = f"Check{standard_id}"
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(f"class {class_name}:")), None)
    if start is None:
        return check_file.read_text(encoding="utf-8")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("class ") and not lines[i].startswith(f"class {class_name}")),
        len(lines),
    )
    return "\n".join(lines[start:end])


# ── Change-request artifact builder ───────────────────────────────────────────

def _build_request_artifact(body: dict, check_source: str) -> str:
    sid      = body.get("standard_id", "")
    title    = STANDARD_TITLES.get(sid, sid)
    ts       = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    standards_path = Path(__file__).parent / "Record Standards.txt"
    standards_text = standards_path.read_text(encoding="utf-8") if standards_path.is_file() else "(not found)"
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


# ── Effective synonyms (code defaults + config) ────────────────────────────────

def _effective_synonyms() -> dict[str, list[str]]:
    from compliance.extract.sections import SECTION_SYNONYMS
    merged = {k: list(v) for k, v in SECTION_SYNONYMS.items()}
    for canon, syns in cfg.get_section_synonyms().items():
        if isinstance(syns, list):
            merged[canon] = syns
    return merged


def _effective_matrix() -> dict[str, dict[str, str | None]]:
    from compliance.applicability import MATRIX
    import copy
    merged = copy.deepcopy(MATRIX)
    for sid, row in cfg.get_applicability_overrides().items():
        if sid in merged:
            merged[sid].update(row)
        else:
            merged[sid] = row
    return merged


# ── Embedded HTML/CSS/JS ───────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Standards Trainer</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; font-size: 13px;
       display: flex; flex-direction: column; height: 100vh; overflow: hidden;
       background: #f0f2f5; color: #222; }

/* ── top bar ── */
#topbar { background: #1a2340; color: #fff; padding: 6px 14px;
          display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
#topbar h1 { font-size: 14px; font-weight: 600; letter-spacing: .3px; }
#topbar .sub { font-size: 11px; color: #9ab; flex: 1; }
.tb-btn { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2);
          color: #fff; border-radius: 4px; padding: 3px 10px; font-size: 11px;
          cursor: pointer; white-space: nowrap; }
.tb-btn:hover { background: rgba(255,255,255,.22); }
.tb-btn.danger { background: rgba(192,57,43,.5); border-color: rgba(192,57,43,.8); }

/* ── three-pane layout ── */
#layout { display: flex; flex: 1; overflow: hidden; }

/* ── left pane ── */
#left { width: 200px; min-width: 160px; background: #fff; border-right: 1px solid #dde;
        display: flex; flex-direction: column; overflow: hidden; flex-shrink: 0; }
#left h2 { font-size: 11px; font-weight: 700; text-transform: uppercase;
           letter-spacing: .8px; color: #888; padding: 10px 12px 6px; border-bottom: 1px solid #eee; }
#pdf-list { flex: 1; overflow-y: auto; }
.pdf-item { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #f2f2f2; transition: background .12s; }
.pdf-item:hover { background: #f0f4ff; }
.pdf-item.active { background: #e8eeff; border-left: 3px solid #4466cc; padding-left: 9px; }
.pdf-name { font-weight: 500; word-break: break-all; }
.pdf-meta { font-size: 11px; color: #999; margin-top: 2px; }

/* ── center pane ── */
#center { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
#center-header { padding: 8px 12px; background: #fff; border-bottom: 1px solid #dde;
                 font-size: 12px; color: #555; flex-shrink: 0; }
#pdf-frame { flex: 1; border: none; background: #555; }
#pdf-placeholder { flex: 1; display: flex; align-items: center; justify-content: center;
                   color: #aaa; font-size: 14px; }

/* ── right pane ── */
#right { width: 360px; min-width: 280px; background: #f8f9fb; border-left: 1px solid #dde;
         display: flex; flex-direction: column; overflow: hidden; flex-shrink: 0; }
#right-header { padding: 8px 12px; background: #fff; border-bottom: 1px solid #dde;
                font-size: 12px; color: #555; flex-shrink: 0; }
#results-pane { flex: 1; overflow-y: auto; padding: 8px; }
#spinner { display: none; padding: 20px; text-align: center; color: #888; font-size: 12px; }

/* ── accordion ── */
.accordion { background: #fff; border: 1px solid #d8dce8; border-radius: 6px; margin-bottom: 8px; overflow: hidden; }
.acc-header { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
              cursor: pointer; user-select: none; background: #eef0f8; transition: background .12s; }
.acc-header:hover { background: #e4e8f4; }
.chevron { font-size: 10px; color: #778; transition: transform .18s ease; display: inline-block; width: 12px; flex-shrink: 0; }
.accordion.open > .acc-header .chevron { transform: rotate(90deg); }
.acc-note-label { flex: 1; font-size: 11px; font-weight: 700; text-transform: uppercase;
                  letter-spacing: .5px; color: #334; line-height: 1.3; }
.acc-summary { display: flex; gap: 4px; flex-shrink: 0; }
.acc-body { max-height: 0; overflow: hidden; transition: max-height .22s ease; }
.accordion.open > .acc-body { max-height: 9999px; }
.acc-body-inner { padding: 6px; }

/* ── cards ── */
.card { background: #fff; border: 1px solid #e0e4ec; border-radius: 5px;
        margin-bottom: 4px; padding: 6px 8px; cursor: pointer;
        transition: box-shadow .12s, border-color .12s; }
.card:hover { box-shadow: 0 1px 6px rgba(0,0,0,.10); border-color: #aac; }
.card.na { background: #f6f6f6; border-color: #e8e8e8; cursor: default; opacity: .5; }
.card-top { display: flex; align-items: center; gap: 6px; }
.card-id { font-size: 10px; font-weight: 700; color: #888; min-width: 32px; }
.card-title { flex: 1; font-size: 11px; color: #333; line-height: 1.3; }
.badge { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 10px;
         font-weight: 700; color: #fff; white-space: nowrap; }
.badge-pass           { background: #2d7a2d; }
.badge-fail           { background: #c0392b; }
.badge-manual_review  { background: #e67e22; }
.badge-not_applicable { background: #aaa; }
.card-rationale { font-size: 10px; color: #777; margin-top: 3px; line-height: 1.3;
                  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* ── buttons ── */
.btn { display: inline-block; padding: 4px 11px; border-radius: 4px; font-size: 11px;
       font-weight: 600; cursor: pointer; border: 1px solid transparent; }
.btn-primary  { background: #4466cc; color: #fff; }
.btn-primary:hover  { background: #2244aa; }
.btn-success  { background: #2d7a2d; color: #fff; }
.btn-success:hover  { background: #1a5a1a; }
.btn-warn     { background: #e67e22; color: #fff; }
.btn-warn:hover     { background: #c0641a; }
.btn-danger   { background: #c0392b; color: #fff; }
.btn-danger:hover   { background: #922b21; }
.btn-ghost    { background: #fff; color: #444; border-color: #ccc; }
.btn-ghost:hover    { background: #f5f5f5; }
.btn-row      { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }

/* ── modal ── */
#modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.45);
                 z-index: 1000; align-items: center; justify-content: center; }
#modal-overlay.open { display: flex; }
#modal { background: #fff; border-radius: 8px; width: 720px; max-width: 96vw;
         max-height: 88vh; display: flex; flex-direction: column;
         box-shadow: 0 8px 40px rgba(0,0,0,.25); }
#modal-header { padding: 14px 18px; border-bottom: 1px solid #eee;
                display: flex; align-items: flex-start; gap: 10px; }
#modal-header-text { flex: 1; }
#modal-title { font-size: 14px; font-weight: 700; }
#modal-subtitle { font-size: 11px; color: #777; margin-top: 2px; }
#modal-close { background: none; border: none; font-size: 18px; cursor: pointer;
               color: #aaa; line-height: 1; padding: 0 4px; }
#modal-close:hover { color: #333; }
#modal-body { flex: 1; overflow-y: auto; padding: 14px 18px; }

.section-label { font-size: 10px; font-weight: 700; text-transform: uppercase;
                 letter-spacing: .8px; color: #888; margin: 14px 0 6px; }
.section-label:first-child { margin-top: 0; }
.verdict-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.rationale-text { font-size: 12px; color: #333; line-height: 1.5; }
.excerpt-box { background: #fffbea; border-left: 3px solid #e6c800; padding: 5px 8px;
               margin: 4px 0; font-size: 11px; font-family: monospace;
               white-space: pre-wrap; border-radius: 2px; }
.page-btn { display: inline-block; background: #4466cc; color: #fff; border: none;
            border-radius: 3px; padding: 2px 8px; font-size: 11px; cursor: pointer; margin: 2px; }
.page-btn:hover { background: #2244aa; }
.judge-call { background: #f4f6fc; border: 1px solid #dde; border-radius: 4px;
              padding: 8px 10px; margin: 6px 0; font-size: 11px; }
.judge-q { font-weight: 600; color: #334; margin-bottom: 4px; }
.judge-q-eff { font-style: italic; color: #3a6a3a; margin-bottom: 4px; }
.judge-ctx { color: #777; font-family: monospace; font-size: 10px; white-space: pre-wrap;
             max-height: 100px; overflow-y: auto; background: #fafafa;
             padding: 4px 6px; border-radius: 2px; margin: 4px 0; }
.judge-answer { margin-top: 4px; }
.input-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.input-table td { padding: 3px 6px; border-bottom: 1px solid #f0f0f0; }
.input-table td:first-child { font-weight: 600; color: #556; width: 42%; }
.sections-list { font-size: 10px; color: #778; font-family: monospace; line-height: 1.6; }
.appl-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; }
.appl-R    { background: #e8f5e9; color: #2e7d32; }
.appl-C    { background: #fff3e0; color: #e65100; }
.appl-none { background: #f0f0f0; color: #aaa; }
.override-note { font-size: 10px; color: #e67e22; margin-left: 6px; }

/* ── edit panels ── */
.edit-panel { background: #f0f4ff; border: 1px solid #c0c8e8; border-radius: 5px;
              padding: 10px 12px; margin: 8px 0; }
.edit-panel h4 { font-size: 11px; font-weight: 700; color: #334; margin-bottom: 8px; }
.synonym-list { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.synonym-chip { background: #e8ecf8; border: 1px solid #bcc8e8; border-radius: 12px;
                padding: 2px 10px; font-size: 10px; font-family: monospace;
                display: inline-flex; align-items: center; gap: 4px; }
.rm-syn { cursor: pointer; color: #c0392b; font-weight: 700; }
.rm-syn:hover { color: #922b21; }
.missing-section { background: #fff5f5; border-left: 3px solid #c0392b; padding: 4px 8px;
                   font-size: 11px; margin: 3px 0; border-radius: 2px;
                   display: flex; align-items: center; gap: 8px; }
.syn-add-row { display: flex; gap: 6px; }
.syn-add-row input { flex: 1; font-size: 11px; padding: 4px 6px;
                     border: 1px solid #ccd; border-radius: 3px; }
.prompt-editor textarea { width: 100%; min-height: 90px; font-size: 11px;
                          font-family: monospace; border: 1px solid #ccd;
                          border-radius: 3px; padding: 6px; resize: vertical; }
.test-result { background: #f9f9f9; border: 1px solid #dde; border-radius: 4px;
               padding: 8px 10px; margin-top: 8px; font-size: 11px; }
.test-result.pass { border-color: #2d7a2d; background: #f0fff0; }
.test-result.fail { border-color: #c0392b; background: #fff0f0; }
.test-result.manual_review { border-color: #e67e22; background: #fff8f0; }
.save-feedback { font-size: 10px; color: #2d7a2d; margin-left: 8px; display: none; }

/* ── regression panel ── */
#reg-panel { position: fixed; top: 38px; right: 362px; width: 440px; max-height: 55vh;
             background: #fff; border: 1px solid #dde; border-radius: 6px 0 0 6px;
             box-shadow: -4px 4px 20px rgba(0,0,0,.15); z-index: 500;
             display: none; flex-direction: column; overflow: hidden; }
#reg-panel.open { display: flex; }
#reg-header { padding: 9px 14px; background: #1a2340; color: #fff; font-size: 12px;
              font-weight: 600; display: flex; align-items: center; gap: 8px; }
#reg-body { flex: 1; overflow-y: auto; padding: 8px; }
.delta-row { display: flex; gap: 8px; align-items: center; padding: 4px 6px;
             border-bottom: 1px solid #f0f0f0; font-size: 11px; border-radius: 3px; }
.delta-row.ok { background: #f0fff0; }
.delta-row.bad { background: #fff0f0; }
.delta-label { flex: 1; }

/* ── change-request modal ── */
#cr-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.55);
              z-index: 2000; align-items: center; justify-content: center; }
#cr-overlay.open { display: flex; }
#cr-modal { background: #fff; border-radius: 8px; width: 760px; max-width: 96vw;
            max-height: 88vh; display: flex; flex-direction: column;
            box-shadow: 0 8px 40px rgba(0,0,0,.3); }
#cr-header { padding: 12px 16px; background: #1a2340; color: #fff;
             border-radius: 8px 8px 0 0; display: flex; align-items: center; gap: 10px; }
#cr-header span { flex: 1; font-size: 13px; font-weight: 600; }
#cr-body { flex: 1; overflow-y: auto; padding: 14px 16px; }
#cr-body textarea { width: 100%; min-height: 60px; font-size: 11px; font-family: monospace;
                    border: 1px solid #ccd; border-radius: 3px; padding: 6px; resize: vertical; }
#cr-md { background: #f4f6fa; border: 1px solid #dde; border-radius: 4px; padding: 10px;
         font-size: 10px; font-family: monospace; white-space: pre-wrap; word-break: break-word;
         max-height: 300px; overflow-y: auto; margin-top: 10px; }
</style>
</head>
<body>

<div id="topbar">
  <h1>Standards Trainer</h1>
  <span class="sub" id="source-label"></span>
  <button class="tb-btn" onclick="reloadRules()">↺ Reload rules</button>
  <button class="tb-btn" id="reg-btn" onclick="toggleRegression()">Regression <span id="corpus-count">(0)</span></button>
  <button class="tb-btn danger" id="run-reg-btn" onclick="runRegression()" style="display:none">▶ Run</button>
</div>

<div id="layout">
  <div id="left">
    <h2>PDFs</h2>
    <div id="pdf-list"></div>
  </div>
  <div id="center">
    <div id="center-header">Select a PDF to view</div>
    <div id="pdf-placeholder">← Select a PDF from the list</div>
  </div>
  <div id="right">
    <div id="right-header">Standards (47)</div>
    <div id="spinner">Evaluating…</div>
    <div id="results-pane"></div>
  </div>
</div>

<!-- Regression panel -->
<div id="reg-panel">
  <div id="reg-header">
    <span>Regression corpus</span>
    <button class="tb-btn" onclick="toggleRegression()">✕</button>
  </div>
  <div id="reg-body"><p style="padding:8px;font-size:11px;color:#888">Click "Run" to execute pinned checks.</p></div>
</div>

<!-- Main card dialog -->
<div id="modal-overlay">
  <div id="modal">
    <div id="modal-header">
      <div id="modal-header-text">
        <div id="modal-title"></div>
        <div id="modal-subtitle"></div>
      </div>
      <button id="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div id="modal-body"></div>
  </div>
</div>

<!-- Change-request modal -->
<div id="cr-overlay">
  <div id="cr-modal">
    <div id="cr-header">
      <span>Generate change request</span>
      <button class="tb-btn" onclick="closeCR()">✕</button>
    </div>
    <div id="cr-body">
      <p style="font-size:11px;color:#555;margin-bottom:8px">
        Describe the fix. The tool will assemble a complete handoff artifact for
        Claude Code that includes the standard text, current check source, note
        inputs, and hard constraints.
      </p>
      <label style="font-size:11px;font-weight:600">Desired verdict</label><br>
      <select id="cr-desired" style="font-size:11px;margin:4px 0 8px;padding:3px 6px;border:1px solid #ccd;border-radius:3px">
        <option value="pass">pass</option>
        <option value="fail">fail</option>
        <option value="manual_review">manual_review</option>
        <option value="not_applicable">not_applicable</option>
      </select><br>
      <label style="font-size:11px;font-weight:600">Describe the change needed</label><br>
      <textarea id="cr-desc" placeholder="e.g. The check should also recognise 'social and psychiatric history' as the psychiatric history section…" style="margin-top:4px"></textarea>
      <div class="btn-row">
        <button class="btn btn-primary" onclick="generateCR()">Generate artifact</button>
        <button class="btn btn-ghost" onclick="closeCR()">Cancel</button>
      </div>
      <div id="cr-result" style="display:none">
        <p style="font-size:11px;color:#2d7a2d;margin:10px 0 4px">
          ✓ Written to <code id="cr-file"></code>
        </p>
        <div class="btn-row" style="margin-bottom:8px">
          <button class="btn btn-ghost" onclick="copyCR()">Copy to clipboard</button>
        </div>
        <pre id="cr-md"></pre>
      </div>
    </div>
  </div>
</div>

<script>
"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let _currentPdf    = null;
let _currentIframe = null;
let _noteData      = [];
let _currentNote   = null;
let _currentCard   = null;
let _corpus        = [];
let _crMd          = "";

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  const [pdfs, corpus] = await Promise.all([
    fetch("/api/pdfs").then(r => r.json()),
    fetch("/api/regression/corpus").then(r => r.json()),
  ]);
  document.getElementById("source-label").textContent = "Source: " + pdfs.source_dir;
  _corpus = corpus;
  updateCorpusCount();

  const list = document.getElementById("pdf-list");
  pdfs.pdfs.forEach(pdf => {
    const el = document.createElement("div");
    el.className = "pdf-item";
    el.dataset.name = pdf.name;
    el.innerHTML = `<div class="pdf-name">${pdf.name}</div>
                    <div class="pdf-meta">${pdf.note_count} note${pdf.note_count !== 1 ? "s" : ""}</div>`;
    el.addEventListener("click", () => selectPdf(pdf.name, el));
    list.appendChild(el);
  });
}

// ── PDF selection ─────────────────────────────────────────────────────────────
async function selectPdf(name, el) {
  if (_currentPdf === name) return;
  _currentPdf = name;
  document.querySelectorAll(".pdf-item").forEach(e => e.classList.remove("active"));
  el.classList.add("active");
  loadPdfViewer(name, 1);

  const pane = document.getElementById("results-pane");
  pane.innerHTML = "";
  pane.scrollTop = 0;
  document.getElementById("right-header").textContent = "Evaluating…";
  document.getElementById("spinner").style.display = "block";

  try {
    const notes = await fetch(`/api/evaluate?pdf=${encodeURIComponent(name)}`).then(r => r.json());
    _noteData = notes;
    renderResults(notes);
  } catch (e) {
    pane.innerHTML = `<div style="padding:12px;color:#c00">Error: ${e.message}</div>`;
  } finally {
    document.getElementById("spinner").style.display = "none";
  }
}

function loadPdfViewer(name, page) {
  const center = document.getElementById("center");
  const ph = document.getElementById("pdf-placeholder");
  if (ph) ph.remove();
  const src = `/pdf/${encodeURIComponent(name)}#page=${page}`;
  if (_currentIframe) {
    _currentIframe.src = src;
  } else {
    const iframe = document.createElement("iframe");
    iframe.id = "pdf-frame";
    iframe.style.cssText = "flex:1;border:none;background:#555;";
    iframe.src = src;
    center.appendChild(iframe);
    _currentIframe = iframe;
  }
  document.getElementById("center-header").textContent = `${name}  —  page ${page}`;
}

function jumpToPage(page) {
  if (_currentPdf) loadPdfViewer(_currentPdf, page);
}

// ── Accordion ─────────────────────────────────────────────────────────────────
function toggleAccordion(id, jumpPage) {
  const acc   = document.getElementById(id);
  const isOpen = acc.classList.contains("open");
  document.querySelectorAll(".accordion").forEach(a => a.classList.remove("open"));
  if (!isOpen) {
    acc.classList.add("open");
    acc.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (jumpPage) jumpToPage(jumpPage);
  }
}

// ── Results ───────────────────────────────────────────────────────────────────
function verdictBadge(verdict) {
  const labels = { pass:"PASS", fail:"FAIL", manual_review:"REVIEW", not_applicable:"N/A" };
  return `<span class="badge badge-${verdict}">${labels[verdict] || verdict.toUpperCase()}</span>`;
}

function renderResults(notes) {
  const pane = document.getElementById("results-pane");
  pane.innerHTML = "";
  const failCount = notes.reduce((s,n) => s + n.cards.filter(c=>c.verdict==="fail").length, 0);
  const mrCount   = notes.reduce((s,n) => s + n.cards.filter(c=>c.verdict==="manual_review").length, 0);
  document.getElementById("right-header").textContent = `Standards — ${failCount} fail · ${mrCount} review`;

  notes.forEach((note, ni) => {
    const accId = `acc-${ni}`;
    const noteFail = note.cards.filter(c=>c.verdict==="fail").length;
    const noteMr   = note.cards.filter(c=>c.verdict==="manual_review").length;
    const summaryBadges = [
      noteFail > 0 ? `<span class="badge badge-fail">${noteFail} fail</span>` : "",
      noteMr   > 0 ? `<span class="badge badge-manual_review">${noteMr} review</span>` : "",
    ].filter(Boolean).join(" ");

    const acc = document.createElement("div");
    acc.className = "accordion";
    acc.id = accId;

    const header = document.createElement("div");
    header.className = "acc-header";
    header.innerHTML = `
      <span class="chevron">▶</span>
      <span class="acc-note-label">Note ${ni+1}: ${escHtml(note.note_type.replace(/_/g," "))} · ${escHtml(note.member)} · ${escHtml(note.service_date||"—")}</span>
      <span class="acc-summary">${summaryBadges}</span>`;
    header.addEventListener("click", () => toggleAccordion(accId, note.first_page));
    acc.appendChild(header);

    const body = document.createElement("div");
    body.className = "acc-body";
    const inner = document.createElement("div");
    inner.className = "acc-body-inner";

    note.cards.forEach(card => {
      const isNA = card.applicability === null;
      const div  = document.createElement("div");
      div.className = "card" + (isNA ? " na" : "");
      div.innerHTML = `
        <div class="card-top">
          <span class="card-id">${card.standard_id}</span>
          ${verdictBadge(card.verdict)}
          <span class="card-title">${escHtml(card.title)}</span>
        </div>
        <div class="card-rationale">${escHtml(card.rationale)}</div>`;
      if (!isNA) div.addEventListener("click", () => openModal(note, card));
      inner.appendChild(div);
    });

    body.appendChild(inner);
    acc.appendChild(body);
    pane.appendChild(acc);
  });

  const first = pane.querySelector(".accordion");
  if (first) {
    first.classList.add("open");
    if (_noteData[0]) jumpToPage(_noteData[0].first_page);
  }
}

// ── Main dialog ───────────────────────────────────────────────────────────────
function openModal(note, card) {
  _currentNote = note;
  _currentCard = card;
  const overlay = document.getElementById("modal-overlay");
  const applLabel = card.applicability==="R" ? "Required" : card.applicability==="C" ? "Conditional" : "Not applicable";
  const applClass = card.applicability || "none";

  document.getElementById("modal-title").textContent = `${card.standard_id} — ${card.title}`;
  document.getElementById("modal-subtitle").textContent =
    `${note.note_type.replace(/_/g," ")} · ${note.member} · ${note.service_date||"—"}`;

  let html = "";

  // 1. Applicability + verdict
  html += `<div class="section-label">Applicability &amp; Verdict</div>
    <div class="verdict-row">
      <span class="appl-badge appl-${applClass}">${applLabel}</span>
      ${verdictBadge(card.verdict)}
    </div>
    <div class="rationale-text">${escHtml(card.rationale)}</div>`;

  // 2. Evidence
  if (card.excerpts?.length > 0) {
    html += `<div class="section-label">Evidence</div>`;
    card.excerpts.forEach(ex => { html += `<div class="excerpt-box">${escHtml(ex)}</div>`; });
  }

  // 3. Page buttons
  if (card.page_numbers?.length > 0) {
    html += `<div class="section-label">Source pages</div>`;
    card.page_numbers.forEach(pg => {
      html += `<button class="page-btn" onclick="jumpToPage(${pg});closeModal()">Jump to page ${pg}</button>`;
    });
  }

  // 4. Judge path + prompt editor
  if (card.judge_calls?.length > 0) {
    html += `<div class="section-label">Judge path (${escHtml(card.judge_used||"null")})</div>`;
    card.judge_calls.forEach((call, i) => {
      const overrideNote = call.prompt_overridden
        ? `<span class="override-note">⚠ prompt overridden by rules/prompts/${card.standard_id}.md</span>` : "";
      html += `<div class="judge-call">
        <div class="judge-q">Original question ${i+1}: ${escHtml(call.question)}</div>
        ${call.prompt_overridden ? `<div class="judge-q-eff">Effective (override): ${escHtml(call.effective_question)}</div>` : ""}
        <div class="judge-ctx">${escHtml(call.context)}</div>
        <div class="judge-answer">${verdictBadge(call.verdict)} <span style="font-size:11px;margin-left:6px">${escHtml(call.rationale)}</span>${overrideNote}</div>
      </div>`;
    });

    // Prompt editor
    const currentQ = card.judge_calls[0].effective_question || card.judge_calls[0].question;
    html += `<div class="edit-panel" id="prompt-panel">
      <h4>✏ Edit judge prompt${card.judge_calls[0].prompt_overridden ? " (override active)" : ""}</h4>
      <div class="prompt-editor">
        <textarea id="prompt-text">${escHtml(currentQ)}</textarea>
        <div class="btn-row">
          <button class="btn btn-primary" onclick="testPrompt()">Test against this note</button>
          <button class="btn btn-success" onclick="savePrompt()">Save prompt</button>
          ${card.judge_calls[0].prompt_overridden
            ? `<button class="btn btn-warn" onclick="deletePrompt()">Remove override</button>` : ""}
          <span class="save-feedback" id="prompt-saved">✓ Saved</span>
        </div>
        <div id="prompt-test-result" style="display:none" class="test-result"></div>
      </div>
    </div>`;
  } else {
    html += `<div class="section-label">Judge path</div>
      <div style="font-size:11px;color:#888">Rule-only check — no judge invoked.</div>`;
  }

  // 5. Rule inputs — header fields
  html += `<div class="section-label">Rule inputs — header fields</div>
    <table class="input-table">`;
  Object.entries(note.header).forEach(([k, v]) => {
    const val = Array.isArray(v) ? v.join(", ") : String(v ?? "—");
    html += `<tr><td>${escHtml(k)}</td><td>${escHtml(val)}</td></tr>`;
  });
  html += `</table>`;

  // 6. Sections extracted
  html += `<div class="section-label">Rule inputs — sections extracted from note</div>`;
  if (note.section_keys.length > 0) {
    html += `<div class="sections-list">${note.section_keys.map(escHtml).join("  ·  ")}</div>`;
  } else {
    html += `<div style="font-size:11px;color:#aaa">No named sections extracted.</div>`;
  }

  // 7. Synonym editor — sections searched but not found
  if (card.sections_missing?.length > 0) {
    html += `<div class="section-label">Tier 1: Sections not found — add synonyms to fix</div>`;
    card.sections_missing.forEach(canon => {
      html += `<div class="missing-section">
        <strong>${escHtml(canon)}</strong> not found as a named section.
        <button class="btn btn-primary" style="padding:2px 8px;font-size:10px"
          onclick="openSynonymEditor('${escHtml(canon)}')">Edit synonyms</button>
      </div>`;
    });
    html += `<div id="synonym-panel"></div>`;
  }

  // 8. Applicability editor
  html += `<div class="section-label">Tier 1: Applicability</div>
    <div style="font-size:11px;color:#555;margin-bottom:6px">
      Current applicability for <strong>${note.note_type}</strong>:
      <span class="appl-badge appl-${applClass}">${applLabel}</span>
    </div>
    <div class="btn-row">
      <button class="btn btn-ghost" onclick="openApplEditor()">Edit applicability matrix</button>
    </div>
    <div id="appl-panel"></div>`;

  // 9. Actions
  html += `<div class="section-label">Actions</div>`;
  const isPinned = _corpus.some(e =>
    e.pdf === _currentPdf && e.note_index === note.note_index && e.standard_id === card.standard_id);
  html += `<div class="btn-row">
    <button class="btn ${isPinned ? "btn-danger" : "btn-ghost"}"
      onclick="${isPinned ? "unpinVerdict()" : "pinVerdict()"}">
      📌 ${isPinned ? "Unpin from corpus" : "Pin verdict to corpus"}
    </button>
    <button class="btn btn-ghost" onclick="openCR()">Tier 3a: Generate change request</button>
  </div>`;

  document.getElementById("modal-body").innerHTML = html;
  overlay.classList.add("open");
}

function closeModal() { document.getElementById("modal-overlay").classList.remove("open"); }
document.getElementById("modal-overlay").addEventListener("click", e => { if (e.target.id==="modal-overlay") closeModal(); });
document.addEventListener("keydown", e => { if (e.key==="Escape") { closeModal(); closeCR(); } });

// ── Synonym editor ────────────────────────────────────────────────────────────
let _synEditorCanon = null;
let _synEditorData  = {};

async function openSynonymEditor(canon) {
  _synEditorCanon = canon;
  const allSyns = await fetch("/api/config/synonyms").then(r => r.json());
  _synEditorData  = JSON.parse(JSON.stringify(allSyns)); // deep copy
  const current   = allSyns[canon] || [];
  const panel     = document.getElementById("synonym-panel");

  panel.innerHTML = `
    <div class="edit-panel" style="margin-top:4px">
      <h4>Synonyms for <code>${escHtml(canon)}</code></h4>
      <div class="synonym-list" id="syn-chips">
        ${current.map(s => synChip(s, canon)).join("")}
      </div>
      <div class="syn-add-row">
        <input id="syn-input" type="text" placeholder="New synonym phrase…"
          onkeydown="if(event.key==='Enter'){event.preventDefault();addSyn();}">
        <button class="btn btn-primary" onclick="addSyn()">Add</button>
      </div>
      <div class="btn-row" style="margin-top:8px">
        <button class="btn btn-success" onclick="saveSynonyms()">Save &amp; re-evaluate</button>
        <button class="btn btn-ghost" onclick="document.getElementById('synonym-panel').innerHTML=''">Cancel</button>
        <span class="save-feedback" id="syn-saved">✓ Saved — re-evaluating…</span>
      </div>
    </div>`;
}

function synChip(s, canon) {
  return `<span class="synonym-chip">${escHtml(s)}<span class="rm-syn" onclick="removeSyn('${escHtml(s)}')" title="Remove">×</span></span>`;
}

function removeSyn(s) {
  if (!_synEditorCanon) return;
  const list = _synEditorData[_synEditorCanon] || [];
  _synEditorData[_synEditorCanon] = list.filter(x => x !== s);
  refreshSynChips();
}

function addSyn() {
  if (!_synEditorCanon) return;
  const inp = document.getElementById("syn-input");
  const val = inp.value.trim().toLowerCase();
  if (!val) return;
  const list = _synEditorData[_synEditorCanon] || [];
  if (!list.includes(val)) {
    _synEditorData[_synEditorCanon] = [...list, val];
  }
  inp.value = "";
  refreshSynChips();
}

function refreshSynChips() {
  const canon = _synEditorCanon;
  const list  = _synEditorData[canon] || [];
  document.getElementById("syn-chips").innerHTML = list.map(s => synChip(s, canon)).join("");
}

async function saveSynonyms() {
  const fb = document.getElementById("syn-saved");
  await fetch("/api/config/synonyms", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(_synEditorData),
  });
  fb.style.display = "inline";
  // Re-evaluate current PDF and refresh
  await reEvalCurrent();
  setTimeout(() => { fb.style.display = "none"; }, 3000);
}

// ── Applicability editor ──────────────────────────────────────────────────────
async function openApplEditor() {
  const panel = document.getElementById("appl-panel");
  if (panel.innerHTML) { panel.innerHTML = ""; return; }
  const matrix = await fetch("/api/config/applicability").then(r => r.json());
  const sid    = _currentCard.standard_id;
  const row    = matrix[sid] || {};
  const types  = ["intake","progress","consultation","treatment_plan","discharge","group","family"];
  let html = `<div class="edit-panel" style="margin-top:4px"><h4>Applicability — ${sid}</h4>
    <table class="input-table"><thead><tr><th>Doc type</th><th>Applicability</th></tr></thead><tbody>`;
  types.forEach(t => {
    const val = row[t] ?? "";
    html += `<tr><td>${t}</td><td>
      <select id="appl-${t}" style="font-size:11px;padding:2px 4px;border:1px solid #ccd;border-radius:3px">
        <option value=""${!val?" selected":""}>— (not applicable)</option>
        <option value="R"${val==="R"?" selected":""}>R (required)</option>
        <option value="C"${val==="C"?" selected":""}>C (conditional)</option>
      </select></td></tr>`;
  });
  html += `</tbody></table>
    <div class="btn-row" style="margin-top:8px">
      <button class="btn btn-success" onclick="saveApplicability('${sid}')">Save applicability</button>
      <span class="save-feedback" id="appl-saved">✓ Saved</span>
    </div></div>`;
  panel.innerHTML = html;
}

async function saveApplicability(sid) {
  const types = ["intake","progress","consultation","treatment_plan","discharge","group","family"];
  const row   = {};
  types.forEach(t => {
    const v = document.getElementById(`appl-${t}`)?.value;
    row[t]  = v || null;
  });
  const overrides = await fetch("/api/config/applicability").then(r => r.json());
  overrides[sid]  = row;
  await fetch("/api/config/applicability", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(overrides),
  });
  const fb = document.getElementById("appl-saved");
  fb.style.display = "inline";
  await reEvalCurrent();
  setTimeout(() => { fb.style.display = "none"; }, 3000);
}

// ── Prompt editor ─────────────────────────────────────────────────────────────
async function testPrompt() {
  const q    = document.getElementById("prompt-text").value.trim();
  const ctx  = _currentCard.judge_calls?.[0]?.context || "";
  const res  = await fetch(`/api/prompts/${_currentCard.standard_id}/test`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ question: q, context: ctx }),
  }).then(r => r.json());
  const el = document.getElementById("prompt-test-result");
  el.style.display = "block";
  el.className     = `test-result ${res.verdict || ""}`;
  el.innerHTML = res.error
    ? `Error: ${escHtml(res.error)}`
    : `${verdictBadge(res.verdict)} ${escHtml(res.rationale)}`;
}

async function savePrompt() {
  const q = document.getElementById("prompt-text").value.trim();
  await fetch(`/api/prompts/${_currentCard.standard_id}/save`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ prompt: q }),
  });
  const fb = document.getElementById("prompt-saved");
  fb.style.display = "inline";
  await reEvalCurrent();
  setTimeout(() => { fb.style.display = "none"; }, 3000);
}

async function deletePrompt() {
  await fetch(`/api/prompts/${_currentCard.standard_id}/delete`, { method: "POST" });
  await reEvalCurrent();
  closeModal();
}

// ── Regression corpus ─────────────────────────────────────────────────────────
function updateCorpusCount() {
  document.getElementById("corpus-count").textContent = `(${_corpus.length})`;
}

function toggleRegression() {
  const panel = document.getElementById("reg-panel");
  const runBtn = document.getElementById("run-reg-btn");
  const open   = panel.classList.toggle("open");
  runBtn.style.display = open ? "inline-block" : "none";
}

async function pinVerdict() {
  const entry = {
    pdf:              _currentPdf,
    note_index:       _currentNote.note_index,
    standard_id:      _currentCard.standard_id,
    expected_verdict: _currentCard.verdict,
    rationale:        _currentCard.rationale.slice(0, 120),
  };
  const res = await fetch("/api/regression/pin", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(entry),
  }).then(r => r.json());
  _corpus = await fetch("/api/regression/corpus").then(r => r.json());
  updateCorpusCount();
  closeModal();
}

async function unpinVerdict() {
  await fetch("/api/regression/unpin", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      pdf: _currentPdf,
      note_index: _currentNote.note_index,
      standard_id: _currentCard.standard_id,
    }),
  });
  _corpus = await fetch("/api/regression/corpus").then(r => r.json());
  updateCorpusCount();
  closeModal();
}

async function runRegression() {
  const body = document.getElementById("reg-body");
  body.innerHTML = `<p style="padding:8px;font-size:11px;color:#888">Running…</p>`;
  const data = await fetch("/api/regression/run").then(r => r.json());
  _corpus = await fetch("/api/regression/corpus").then(r => r.json());

  let html = `<div style="padding:6px 8px;font-size:11px;font-weight:600;color:${data.failed>0?"#c00":"#2d7a2d"}">
    ${data.passed}/${data.total} passed (${data.failed} regressions)
  </div>`;
  (data.results || []).forEach(r => {
    const ok = r.match;
    html += `<div class="delta-row ${ok?"ok":"bad"}">
      <span class="delta-label">
        <strong>${escHtml(r.standard_id)}</strong> · ${escHtml(r.pdf)} note ${r.note_index}
      </span>
      ${verdictBadge(r.expected_verdict)} → ${verdictBadge(r.actual)}
      ${!ok ? `<span style="color:#c00;font-weight:700">✗</span>` : `<span style="color:#2d7a2d">✓</span>`}
    </div>`;
  });
  body.innerHTML = html || `<p style="padding:8px;font-size:11px;color:#888">No pinned items.</p>`;
}

// ── Tier 3a — Change request ──────────────────────────────────────────────────
function openCR() {
  closeModal();
  document.getElementById("cr-result").style.display = "none";
  document.getElementById("cr-desc").value = "";
  document.getElementById("cr-desired").value = _currentCard?.verdict || "pass";
  document.getElementById("cr-overlay").classList.add("open");
}
function closeCR() { document.getElementById("cr-overlay").classList.remove("open"); }

async function generateCR() {
  const desired = document.getElementById("cr-desired").value;
  const desc    = document.getElementById("cr-desc").value.trim();
  const body    = {
    standard_id:      _currentCard.standard_id,
    note_type:        _currentNote.note_type,
    member:           _currentNote.member,
    service_date:     _currentNote.service_date,
    section_keys:     _currentNote.section_keys,
    sections_searched: _currentCard.sections_searched,
    sections_missing:  _currentCard.sections_missing,
    header:           _currentNote.header,
    current_verdict:  _currentCard.verdict,
    current_rationale: _currentCard.rationale,
    judge_calls:      _currentCard.judge_calls,
    desired_verdict:  desired,
    description:      desc,
  };
  const res = await fetch("/api/generate-request", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  }).then(r => r.json());
  _crMd = res.markdown || "";
  document.getElementById("cr-file").textContent = res.file || "";
  document.getElementById("cr-md").textContent   = _crMd;
  document.getElementById("cr-result").style.display = "block";
}

async function copyCR() {
  await navigator.clipboard.writeText(_crMd).catch(() => {});
}

// ── Reload rules ──────────────────────────────────────────────────────────────
async function reloadRules() {
  await fetch("/api/reload", { method: "POST" });
  if (_currentPdf) await reEvalCurrent();
}

async function reEvalCurrent() {
  if (!_currentPdf) return;
  const pane = document.getElementById("results-pane");
  document.getElementById("spinner").style.display = "block";
  try {
    const notes = await fetch(`/api/evaluate?pdf=${encodeURIComponent(_currentPdf)}`).then(r => r.json());
    _noteData   = notes;
    renderResults(notes);
  } finally {
    document.getElementById("spinner").style.display = "none";
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

init();
</script>
</body>
</html>
"""


# ── Flask app ─────────────────────────────────────────────────────────────────

def create_app(source_dir: Path, inner_judge) -> object:
    try:
        from flask import Flask, jsonify, request, send_from_directory, abort
    except ImportError:
        sys.exit("Flask is required: pip install flask")

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # ── basic pages / PDF serving ──────────────────────────────────────────────

    @app.route("/")
    def index():
        return _HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/pdfs")
    def api_pdfs():
        pdfs = []
        for p in sorted(source_dir.glob("*.pdf")):
            try:
                notes = split_notes(p)
                count = len(notes)
            except Exception:
                count = 0
            pdfs.append({"name": p.name, "note_count": count})
        return jsonify({"source_dir": str(source_dir), "pdfs": pdfs})

    @app.route("/pdf/<path:name>")
    def serve_pdf(name: str):
        candidate = (source_dir / name).resolve()
        if source_dir.resolve() not in candidate.parents:
            abort(403)
        return send_from_directory(str(source_dir.resolve()), name, mimetype="application/pdf")

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
        try:
            result = evaluate_pdf(candidate, inner_judge)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify(result)

    # ── Tier 1: config routes ──────────────────────────────────────────────────

    @app.route("/api/config/synonyms", methods=["GET", "POST"])
    def api_synonyms():
        path = cfg.RULES_DIR / "section_synonyms.yaml"
        if request.method == "GET":
            return jsonify(_effective_synonyms())
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"error": "expected dict"}), 400
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
        cfg.invalidate(path)
        # Clear pattern cache so next extract_sections call rebuilds
        from compliance.extract import sections as sec_mod
        sec_mod._PATTERN_CACHE.clear()
        return jsonify({"ok": True})

    @app.route("/api/config/applicability", methods=["GET", "POST"])
    def api_applicability():
        path = cfg.RULES_DIR / "applicability.yaml"
        if request.method == "GET":
            return jsonify(_effective_matrix())
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"error": "expected dict"}), 400
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
        cfg.invalidate(path)
        return jsonify({"ok": True})

    @app.route("/api/config/thresholds", methods=["GET", "POST"])
    def api_thresholds():
        path = cfg.RULES_DIR / "thresholds.yaml"
        if request.method == "GET":
            return jsonify(cfg.get_thresholds())
        body = request.get_json(force=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(body, f, allow_unicode=True, default_flow_style=False)
        cfg.invalidate(path)
        return jsonify({"ok": True})

    # ── Tier 2: prompt routes ──────────────────────────────────────────────────

    @app.route("/api/prompts/<standard_id>")
    def api_get_prompt(standard_id: str):
        override = cfg.get_prompt(standard_id)
        return jsonify({"standard_id": standard_id, "prompt": override, "overridden": override is not None})

    @app.route("/api/prompts/<standard_id>/save", methods=["POST"])
    def api_save_prompt(standard_id: str):
        body = request.get_json(force=True)
        prompt = body.get("prompt", "")
        path = cfg.RULES_DIR / "prompts" / f"{standard_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        cfg.invalidate(path)
        return jsonify({"ok": True})

    @app.route("/api/prompts/<standard_id>/delete", methods=["POST"])
    def api_delete_prompt(standard_id: str):
        path = cfg.RULES_DIR / "prompts" / f"{standard_id}.md"
        path.unlink(missing_ok=True)
        cfg.invalidate(path)
        return jsonify({"ok": True})

    @app.route("/api/prompts/<standard_id>/test", methods=["POST"])
    def api_test_prompt(standard_id: str):
        body     = request.get_json(force=True)
        question = body.get("question", "")
        context  = body.get("context", "")
        try:
            answer = inner_judge.evaluate(question=question, context=context)
            return jsonify({"verdict": answer.verdict, "rationale": answer.rationale, "excerpts": answer.excerpts})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Regression routes ──────────────────────────────────────────────────────

    @app.route("/api/regression/corpus")
    def api_regression_corpus():
        return jsonify(_load_corpus())

    @app.route("/api/regression/pin", methods=["POST"])
    def api_regression_pin():
        body   = request.get_json(force=True)
        corpus = _load_corpus()
        corpus = [e for e in corpus if not (
            e["pdf"] == body["pdf"] and
            e["note_index"] == body["note_index"] and
            e["standard_id"] == body["standard_id"]
        )]
        body["pinned_at"] = datetime.utcnow().isoformat()
        corpus.append(body)
        _save_corpus(corpus)
        return jsonify({"ok": True, "total": len(corpus)})

    @app.route("/api/regression/unpin", methods=["POST"])
    def api_regression_unpin():
        body   = request.get_json(force=True)
        corpus = [e for e in _load_corpus() if not (
            e["pdf"] == body["pdf"] and
            e["note_index"] == body["note_index"] and
            e["standard_id"] == body["standard_id"]
        )]
        _save_corpus(corpus)
        return jsonify({"ok": True, "total": len(corpus)})

    @app.route("/api/regression/run")
    def api_regression_run():
        corpus  = _load_corpus()
        results = []
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
                bundle = _build_bundles(notes).get(note.header.member_name or "unknown")
                check  = next((c for c in ALL_CHECKS if c.standard_id == entry["standard_id"]), None)
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

    # ── Tier 3a: change request ────────────────────────────────────────────────

    @app.route("/api/generate-request", methods=["POST"])
    def api_generate_request():
        body   = request.get_json(force=True)
        sid    = body.get("standard_id", "unknown")
        ts     = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        source = _read_check_source(sid)
        md     = _build_request_artifact(body, source)
        req_dir = Path(__file__).parent / "rule_requests"
        req_dir.mkdir(exist_ok=True)
        fname  = f"{sid}_{ts}.md"
        (req_dir / fname).write_text(md, encoding="utf-8")
        return jsonify({"markdown": md, "file": str(req_dir / fname)})

    # ── Reload ─────────────────────────────────────────────────────────────────

    @app.route("/api/reload", methods=["POST"])
    def api_reload():
        cfg.invalidate()
        from compliance.extract import sections as sec_mod
        sec_mod._PATTERN_CACHE.clear()
        return jsonify({"ok": True})

    return app


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Standards-evaluation training UI")
    parser.add_argument("--input",  default="sourcedocs", help="Source PDF directory (default: sourcedocs/)")
    parser.add_argument("--port",   type=int, default=5000)
    parser.add_argument("--host",   default="127.0.0.1")
    parser.add_argument(
        "--judge", default="null", choices=["null", "ollama", "claude"],
        help="Judge for prompt testing: null (default), ollama (local), claude (API)",
    )
    parser.add_argument(
        "--ollama-model", default="qwen3.5:9b",
        help="Ollama model name (default: qwen3.5:9b)",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    args = parser.parse_args()

    source_dir = Path(args.input)
    if not source_dir.is_dir():
        sys.exit(f"Input directory not found: {source_dir}")

    if args.judge == "ollama":
        try:
            from compliance.judges.ollama import OllamaJudge
            inner = OllamaJudge(model=args.ollama_model, base_url=args.ollama_url)
            print(f"Using OllamaJudge — model: {args.ollama_model}  url: {args.ollama_url}")
            print("Note: all text stays on-machine (no PHI sent off-network).")
        except Exception as e:
            print(f"Cannot load OllamaJudge: {e}\nFalling back to NullJudge.", file=sys.stderr)
            inner = NullJudge()
    elif args.judge == "claude":
        try:
            from compliance.judges.claude import ClaudeJudge
            inner = ClaudeJudge()
            print("Using ClaudeJudge — PHI WARNING: note text sent to Anthropic API")
        except (ImportError, EnvironmentError) as e:
            print(f"Cannot load ClaudeJudge: {e}\nFalling back to NullJudge.", file=sys.stderr)
            inner = NullJudge()
    else:
        inner = NullJudge()

    app = create_app(source_dir, inner)
    print(f"Standards Trainer — http://{args.host}:{args.port}")
    print(f"Source:  {source_dir.resolve()}")
    print(f"Rules:   {RULES_DIR.resolve()}")
    print(f"Judge:   {getattr(inner, 'name', args.judge)}")
    print("Press Ctrl-C to quit.\n")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
