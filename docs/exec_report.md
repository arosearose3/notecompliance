# Clinical Record Compliance Audit — Executive Report

## What this project does

Reads our clinical PDFs — intake notes, consultation notes, progress notes,
treatment plans, discharge summaries — and grades each one against every
documentation standard we are held to (the items in `Record Standards.txt`).
Output is a per-note pass/fail report listing exactly which standards a note
is missing, with the offending text excerpted.

## Why now

Three needs converge on the same engine:

- **Pre-audit assurance.** Before an external review, a supervisor can
  batch-grade recent records and remediate gaps.
- **Real-time clinician feedback.** A clinician can run the engine on a
  note they just signed and see what is missing before the chart closes.
- **Aggregate reporting.** Findings accumulate so leadership can see
  per-clinician and per-document-type compliance trends.

We build the engine once and ship the three interfaces on top.

## What it covers

Every numbered line of `Record Standards.txt` is mapped to a check. That
includes the universally hard ones: SMART treatment goals, MSE adequacy,
diagnosis-to-assessment alignment, intervention-to-goal alignment,
coordination-of-care at intake/discharge/transitions, late-entry notation,
and telehealth disclosure. Standards that genuinely cannot be assessed from
a PDF (modification audit trail, state-specific telehealth law) are
explicitly flagged as `manual_review` so the audit is never silently
incomplete.

## Approach

A two-track engine: deterministic text rules first, with an optional LLM
"judge" layer for narrative judgment items (SMART goals, MSE quality,
diagnosis support). The rules-only build ships first and is fully useful
on its own; the LLM layer is plugged in later without rework. The decision
between cloud (Claude API) and on-premise LLM is deferred pending PHI
handling clarification.

## Timeline

| Phase | Deliverable | Estimate |
|-------|-------------|----------|
| 0 | Refactor existing PDF code into a reusable engine | 1 week |
| 1 | Section extractor + standards applicability matrix | 1 week |
| 2 | Every rule-based check; end-to-end CSV/HTML reports | 3 weeks |
| 3 | Judge interface wired in (placeholder verdicts) | 1 week |
| 4 | Real LLM judges (gated on PHI decision) | 3+ weeks |
| 5 | CLI + service endpoint + dashboard | parallel to 4 |

A working rules-only audit tool is in hand after Phase 2 (~5 weeks).

## Risks

- **EHR template variance.** Section headers vary between EHR templates;
  if we use more than one template, the section-detection rules need to
  be tuned per template. We need sample PDFs from each.
- **PHI and the LLM judge.** Sending notes to a cloud LLM crosses a PHI
  boundary; an on-premise LLM is weaker. Decision is deferred but
  blocks Phase 4.
- **Cross-note checks.** A few standards (e.g. intervention-to-goal
  alignment) require pairing a progress note with its treatment plan.
  We need a stable way to link notes for the same member and episode of
  care; the canonical key has not been chosen yet.
- **Presence vs quality.** Many standards are written ambiguously
  ("MSE results" — present, or substantive?). Phase 2 grades presence;
  Phase 4 grades quality. Reports will make the distinction explicit so
  a Phase-2 "pass" is not misread as a Phase-4 "pass".

## Open decisions needed from you

The full list is in §10 of `compliance_plan.md`. The three that block
Phase 0:

1. Confirm we are only auditing PDFs in the batch (no EHR lookups).
2. Provide sample PDFs from every EHR template currently in use.
3. Decide whether a BAA with Anthropic is in place; if not, we plan for
   the on-premise LLM path in Phase 4.

The full plan, the per-standard check catalogue, the technical
challenges, and the open-question list are in `docs/compliance_plan.md`.
