"""Per-PDF evaluation: batch and SSE-streaming modes."""

from __future__ import annotations

from pathlib import Path

from compliance.checks.base import not_applicable as make_not_applicable
from compliance.ingest import split_notes
from compliance.models import ContextBundle
from compliance.ruleset import Ruleset, get_ruleset

from trainui.data import SECTIONS_FOR_STANDARD
from trainui.judges import ConfigurableRecordingJudge


def build_bundles(notes) -> dict[str, ContextBundle]:
    bundles: dict[str, ContextBundle] = {}
    for note in notes:
        name = note.header.member_name or "unknown"
        if name not in bundles:
            bundles[name] = ContextBundle(member_name=name, notes=[])
        bundles[name].notes.append(note)
    return bundles


def evaluate_pdf_stream(pdf_path: Path, inner_judge, ruleset: Ruleset | None = None):
    """
    Generator yielding SSE-formatted strings as evaluation progresses.

    Event types:
      init         — {total_notes, total_checks, pdf, ruleset_id}
      note_start   — {note_index, note_type, member, service_date, first_page, total_checks}
      judge_start  — {note_index, standard_id}
      judge_done   — {note_index, standard_id}
      check_done   — {note_index, card: {...}}
      note_done    — {note_index, note: {...}}
      done         — {}
      error        — {message}
    """
    import json as _json

    rs = ruleset or get_ruleset()

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {_json.dumps(data)}\n\n"

    try:
        notes   = split_notes(pdf_path)
        bundles = build_bundles(notes)
    except Exception as exc:
        yield _sse("error", {"message": str(exc)})
        return

    all_checks   = rs.checks()
    total_notes  = len(notes)
    total_checks = len(all_checks)
    yield _sse("init", {
        "total_notes":  total_notes,
        "total_checks": total_checks,
        "pdf":          pdf_path.name,
        "ruleset_id":   rs.id,
    })

    for ni, note in enumerate(notes):
        bundle         = bundles.get(note.header.member_name or "unknown")
        applicable_ids = set(rs.get_applicable_standards(note.note_type))
        h              = note.header

        yield _sse("note_start", {
            "note_index":   ni,
            "note_type":    note.note_type,
            "member":       h.member_name or "Unknown",
            "service_date": str(h.service_date) if h.service_date else None,
            "first_page":   (note.page_indices[0] + 1) if note.page_indices else 1,
            "total_checks": total_checks,
        })

        evaluated: dict[str, tuple] = {}
        for check in all_checks:
            sid = check.standard_id
            if sid not in applicable_ids:
                evaluated[sid] = (make_not_applicable(sid), [])
                continue

            class _StreamingJudge:
                name = getattr(inner_judge, "name", "judge")
                def __init__(self_, calls_out):
                    self_._calls = calls_out
                def evaluate(self_, *, question, context, hint=""):
                    self_._calls.append(("start", sid))
                    ans = ConfigurableRecordingJudge(inner_judge, sid).evaluate(
                        question=question, context=context, hint=hint
                    )
                    self_._calls.append(("done", sid, ans))
                    return ans

            judge_events: list = []
            sj = _StreamingJudge(judge_events)
            rj = ConfigurableRecordingJudge(sj, sid)

            try:
                result = check.run(note, rj, bundle)
            except Exception as exc:
                result = make_not_applicable(sid, f"Check error: {exc}")

            for ev in judge_events:
                if ev[0] == "start":
                    yield _sse("judge_start", {"note_index": ni, "standard_id": sid})
                elif ev[0] == "done":
                    yield _sse("judge_done",  {"note_index": ni, "standard_id": sid})

            actual_calls = rj.calls if hasattr(rj, "calls") else []
            evaluated[sid] = (result, actual_calls)

            sections_searched = SECTIONS_FOR_STANDARD.get(sid, [])
            sections_missing  = [s for s in sections_searched if not note.sections.get(s, "").strip()]
            appl              = rs.applies(sid, note.note_type)
            card = {
                "standard_id":       sid,
                "title":             rs.title(sid),
                "applicability":     appl,
                "verdict":           result.verdict,
                "rationale":         result.rationale,
                "excerpts":          list(result.excerpts),
                "page_numbers":      [p + 1 for p in result.page_numbers],
                "judge_used":        result.judge_used,
                "judge_calls":       actual_calls,
                "sections_searched": sections_searched,
                "sections_missing":  sections_missing,
                "has_prompt_file":   (rs.rules_dir / "prompts" / f"{sid}.md").is_file(),
                "payer_text":        rs.payer_text(sid),
            }
            yield _sse("check_done", {"note_index": ni, "card": card})

        for sid in rs.standard_order:
            if sid in evaluated:
                continue
            appl = rs.applies(sid, note.note_type)
            if appl is not None:
                continue
            sections_searched = SECTIONS_FOR_STANDARD.get(sid, [])
            card = {
                "standard_id":       sid,
                "title":             rs.title(sid),
                "applicability":     None,
                "verdict":           "not_applicable",
                "rationale":         f"Not applicable to {note.note_type} notes.",
                "excerpts":          [],
                "page_numbers":      [],
                "judge_used":        None,
                "judge_calls":       [],
                "sections_searched": sections_searched,
                "sections_missing":  [],
                "has_prompt_file":   (rs.rules_dir / "prompts" / f"{sid}.md").is_file(),
                "payer_text":        rs.payer_text(sid),
            }
            yield _sse("check_done", {"note_index": ni, "card": card})

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

        yield _sse("note_done", {
            "note_index":   ni,
            "note_type":    note.note_type,
            "service_date": str(h.service_date) if h.service_date else None,
            "member":       h.member_name or "Unknown",
            "clinician":    h.clinician or "Unknown",
            "page_indices": note.page_indices,
            "first_page":   (note.page_indices[0] + 1) if note.page_indices else 1,
            "section_keys": sorted(note.sections.keys()),
            "header":       header_snapshot,
        })

    yield _sse("done", {})


def evaluate_pdf(pdf_path: Path, inner_judge, *,
                 note_index: int | None = None,
                 ruleset: Ruleset | None = None) -> list[dict]:
    """
    Run all checks against every note in pdf_path (or only note_index if given).
    Returns a list of per-note dicts for JSON.
    """
    rs      = ruleset or get_ruleset()
    notes   = split_notes(pdf_path)
    bundles = build_bundles(notes)
    note_results = []

    target_indices = [note_index] if note_index is not None else range(len(notes))

    for ni in target_indices:
        if ni >= len(notes):
            continue
        note   = notes[ni]
        bundle = bundles.get(note.header.member_name or "unknown")
        applicable_ids = set(rs.get_applicable_standards(note.note_type))

        evaluated: dict[str, tuple] = {}
        for check in rs.checks():
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
        for sid in rs.standard_order:
            title = rs.title(sid)
            appl  = rs.applies(sid, note.note_type)
            sections_searched = SECTIONS_FOR_STANDARD.get(sid, [])
            sections_missing  = [s for s in sections_searched if not note.sections.get(s, "").strip()]

            if appl is None:
                cards.append({
                    "standard_id":       sid,
                    "title":             title,
                    "applicability":     None,
                    "verdict":           "not_applicable",
                    "rationale":         f"Not applicable to {note.note_type} notes.",
                    "excerpts":          [],
                    "page_numbers":      [],
                    "judge_used":        None,
                    "judge_calls":       [],
                    "sections_searched": sections_searched,
                    "sections_missing":  sections_missing,
                    "has_prompt_file":   (rs.rules_dir / "prompts" / f"{sid}.md").is_file(),
                    "payer_text":        rs.payer_text(sid),
                })
            elif sid in evaluated:
                result, calls = evaluated[sid]
                cards.append({
                    "standard_id":       sid,
                    "title":             title,
                    "applicability":     appl,
                    "verdict":           result.verdict,
                    "rationale":         result.rationale,
                    "excerpts":          list(result.excerpts),
                    "page_numbers":      [p + 1 for p in result.page_numbers],
                    "judge_used":        result.judge_used,
                    "judge_calls":       calls,
                    "sections_searched": sections_searched,
                    "sections_missing":  sections_missing,
                    "has_prompt_file":   (rs.rules_dir / "prompts" / f"{sid}.md").is_file(),
                    "payer_text":        rs.payer_text(sid),
                })
            else:
                cards.append({
                    "standard_id":       sid,
                    "title":             title,
                    "applicability":     appl,
                    "verdict":           "not_applicable",
                    "rationale":         "Check not registered.",
                    "excerpts":          [],
                    "page_numbers":      [],
                    "judge_used":        None,
                    "judge_calls":       [],
                    "sections_searched": sections_searched,
                    "sections_missing":  sections_missing,
                    "has_prompt_file":   False,
                    "payer_text":        rs.payer_text(sid),
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
            "note_index":   ni,
            "note_type":    note.note_type,
            "service_date": str(h.service_date) if h.service_date else None,
            "member":       h.member_name or "Unknown",
            "clinician":    h.clinician or "Unknown",
            "page_indices": note.page_indices,
            "first_page":   (note.page_indices[0] + 1) if note.page_indices else 1,
            "section_keys": sorted(note.sections.keys()),
            "header":       header_snapshot,
            "cards":        cards,
            "ruleset_id":   rs.id,
        })

    return note_results
