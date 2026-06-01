# Clinical Record Compliance Audit — Project Plan

A tool that ingests batches of clinical PDFs (intake notes, consultation notes,
progress notes, treatment plans, discharge summaries) and grades each note
against every item in `Record Standards.txt`, producing per-note findings, a
roll-up dashboard, and (eventually) inline clinician feedback.

This document contains:

1. Executive summary — what we are building and why
2. Scope of inputs and outputs
3. Document type ↔ standards applicability matrix
4. Standards enumeration — every item from `Record Standards.txt`, with the
   intended check for each
5. System architecture
6. Data model
7. Implementation phases (concrete deliverables)
8. Project report — what was planned for, at a glance
9. Technical challenges
10. Open questions that must be answered before full implementation

---

## 1. Executive summary

`fixtnpdf` today fixes one specific field (clinician credential) across PDFs.
This project generalises the same ingestion pipeline into a **compliance audit
engine**. The engine reads PDFs the same way (`pdfplumber` for text,
`pikepdf`/`PyMuPDF` only when we need to write), classifies each note, runs a
list of `Check`s against the relevant standards, and emits structured findings.

Three downstream use cases will share the engine:

- **Internal QA / pre-audit.** A clinician or supervisor runs the engine over a
  batch of completed notes; the output is a CSV + HTML report listing each
  failing standard with the offending excerpt.
- **Real-time clinician feedback.** The same engine is invoked on a single note
  immediately after signing, surfacing missing items so the clinician can
  amend before the chart closes.
- **Aggregate compliance reporting.** Findings are persisted; dashboards
  summarise per-clinician, per-document-type, per-standard pass rates over
  time.

The engine is designed to be **judge-pluggable** — every check has a
deterministic rule path and an optional LLM-judge path. The rules-only build
ships first; the LLM-judge build is layered on without re-architecting.

## 2. Scope

**In scope (V1):**

- Batch ingestion of PDFs from a directory (same layout as `sourcedocs/`).
- Splitting multi-note PDFs into individual notes using the existing
  `Page X of Y` boundary.
- Classifying each note as one of: Intake, Consultation, Progress, Treatment
  Plan, Discharge Summary, Group session note, Family session note, Other.
- Running standard checks scoped to the note's type.
- Emitting findings as JSON, CSV, and a per-note HTML report.

**Explicitly out of scope (V1):**

- Cross-record/chart checks that require data outside the PDF batch
  (the user confirmed the tool sees PDFs only — see Q-INPUTS-1 below).
  Examples: verifying that a signed consent form exists for the member,
  verifying that demographics on file are up to date, longitudinal medication
  reconciliation across episodes of care.
- Detection of edits/strikethroughs (standard B2) — PDFs do not carry the
  revision history needed.
- State-specific telehealth requirements (standard K2). The tool will
  raise a "manual review" flag rather than judge state law.
- Writing/amending PDFs. This engine **reads** PDFs and emits reports;
  amendment workflows belong to a separate tool.

## 3. Document type ↔ standards applicability matrix

Each row is a standard item (see §4 for definitions). `R` = required for this
document type; `C` = conditionally required (e.g. only if meds discussed, only
for adolescents); blank = not applicable.

| Item    | Intake | Tx Plan | Progress | Consult | Discharge |
|---------|:------:|:-------:|:--------:|:-------:|:---------:|
| A1 member ID per page        | R | R | R | R | R |
| A2 demographics/consents     | R |   |   |   |   |
| A3 encounter metadata        | R |   | R | R | R |
| A4 group subject             |   |   | C |   |   |
| A5 family attendees          |   |   | C |   |   |
| B1 late entry notation       | C | C | C | C | C |
| B2 modifications (out of scope V1) | — | — | — | — | — |
| C1 allergies/med conditions  | R |   | C |   | R |
| C2a–d medication tracking    | C |   | C |   | C |
| C2e discharge med list       |   |   |   |   | R |
| D1 presenting problem + MSE  | R |   |   | C |   |
| D2 special status assessment | R |   | C | C |   |
| D3 medical/psych history     | R |   |   |   |   |
| D4 abuse history             | R |   |   |   |   |
| D5 adolescent sexual hx      | C |   |   |   |   |
| D6 child/adol developmental  | C |   |   |   |   |
| D7 12+ substance use         | C |   |   |   |   |
| D8 DSM diagnosis consistent  | R |   |   |   |   |
| D9 functional impairment     | R |   |   |   |   |
| E1 symptoms/problems         |   | R |   |   |   |
| E2 prioritisation            |   | R |   |   |   |
| E3 LOC ↔ impairment          |   | R |   |   |   |
| E4 member involvement        |   | R |   |   |   |
| E5 SMART goals               |   | R |   |   |   |
| E6 goal time frame           |   | R |   |   |   |
| E7 progress noted            |   | R |   |   |   |
| E8 LOS rationale             |   | R |   |   |   |
| E9 goal updates              |   | R |   |   |   |
| E10 re-eval on stagnation    |   | R |   |   |   |
| F1 signature                 |   |   | R |   | R |
| F2 date of service           | R | R | R | R | R |
| F3 telehealth noted          | C | C | C | C | C |
| F4 strengths/limitations     |   |   | R |   |   |
| F5 interventions ↔ goals     |   |   | R |   |   |
| F6 follow-up dates           |   |   | R |   |   |
| F7 missed appt + outreach    |   |   | C |   |   |
| F8 time-based duration       | C |   | R | C |   |
| G1 discharge planning        | R | R | C |   |   |
| H1 reason for episode        |   |   |   |   | R |
| H2 goals achieved summary    |   |   |   |   | R |
| H3 aftercare plan            |   |   |   |   | R |
| I1 coordination of care      | R |   | C | R | R |
| I2 coord at key points       | R |   |   | R | R |
| J1 referrals                 | C |   | C | C | C |
| K1 telehealth noted          | C | C | C | C | C |

(The matrix is encoded as data in `compliance/applicability.py` — never as a
literal table in source — so the report renderer and the check runner read
from the same source of truth.)

## 4. Standards enumeration

Every item in `Record Standards.txt` is listed below with: (a) the line
range it comes from, (b) the document types it applies to, (c) the planned
check approach, and (d) whether the rule path can stand alone or an LLM
judge is recommended.

Notation:

- **Rule path:** how to detect compliance with deterministic text matching.
- **Judge path:** what an LLM would be asked to evaluate where the rule
  path is insufficient (judgment, narrative quality).
- **Verdict:** `pass` / `fail` / `not_applicable` / `manual_review`.

### A. Identification and per-encounter metadata

#### A1. Member name or ID on each page (line 1)

- **Applies:** every document type, every page.
- **Rule path:** extract the `Patient:` field (already present in the
  header; see CLAUDE.md PDF structure) on page 1. For every subsequent
  page in the same note, look for the member identifier on that page.
  Member ID is typically not on every page in the EHR's output — flag
  pages that lack it as `fail`.
- **Judge path:** none required.
- **Verdict:** `pass` if member identifier appears on every page;
  `fail` with list of pages missing it otherwise.

#### A2. Demographics, contacts, consent forms, guardianship (lines 2–4)

- **Applies:** Intake note (and, in V2, the member chart bundle).
- **Rule path:** locate intake sections by header text:
  - Address: regex `(Address|Mailing Address):` plus following non-empty
    line.
  - Employer/school: regex `Employer:|School:`.
  - Home/work phones, emergency contact: regex `Home Phone:|Work Phone:|
    Emergency Contact:`.
  - Marital/legal status: regex `Marital Status:|Legal Status:`.
  - Consent forms: presence of a `Consent:` section or attached consent
    page; absence is a `fail`.
  - Guardianship: regex `Guardian:|Guardianship:` (conditional on
    minor / dependent adult — see Q-DEMO-1).
- **Judge path:** when fields are present but free-text ("lives with
  parents, no formal guardian"), an LLM judge confirms semantic
  presence.
- **Verdict:** per sub-item. Aggregate to `pass` only if all required
  sub-items present.

#### A3. Per-encounter metadata: date of service, duration, attendees, diagnosis, services rendered, clinician name/degree/license/ID (lines 5–7)

- **Applies:** every encounter note (Intake, Progress, Consultation,
  Discharge).
- **Rule path:** reuses extractors from `scanner.py`:
  - Date of service: `RE_DATE`.
  - Duration: `Duration:\s+(\d+\s*minutes)` OR
    `(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)` start/stop.
  - Session attendees: `Participants:` line OR derived from "Member,
    spouse" mentions in body.
  - Diagnosis: `Diagnosis:` section header through next blank line; must
    contain at least one ICD/DSM-style code (regex `[FZ]\d{2}(\.\d+)?`)
    or a recognised DSM phrase.
  - Services rendered: presence of a `Service Code:` field (e.g. 90837)
    — already extractable.
  - Clinician name + degree + license + ID: reuses
    `_extract_license_id` logic from `scanner.py`. Verify the degree
    text (`Licensed Professional Counselor` etc.) matches a
    known-degrees vocabulary.
- **Judge path:** none.
- **Verdict:** per sub-item.

#### A4. Group sessions — subject covered (lines 8–9)

- **Applies:** progress notes flagged as group (`Service Code` in
  group-therapy CPT set, e.g. 90853).
- **Rule path:** locate a `Topic:|Subject:|Session Focus:` section; if
  none, look for free-text describing what was covered.
- **Judge path:** LLM confirms the body identifies a session topic
  rather than only listing attendees.

#### A5. Family sessions — attendees and relationships (line 10)

- **Applies:** progress notes flagged as family (`Service Code` ∈ family
  set, e.g. 90847).
- **Rule path:** `Participants:` line must contain at least two named
  people with a relationship qualifier (`(mother)`, `(spouse)`,
  `(father)`, …).
- **Judge path:** LLM confirms relationships are stated.

### B. Entry integrity

#### B1. Late entry notation (lines 13–15)

- **Applies:** all note types.
- **Rule path:** compare service date (`Date and Time:`) with entry
  date (look for `Entry Date:|Note Created:|Signed on:`). If
  `entry_date - service_date > 24h`, the note must contain the literal
  phrase `late entry` (case-insensitive) AND both dates.
- **Judge path:** none.
- **Verdict:** `not_applicable` when delta ≤ 24h; `fail` when delta
  > 24h and "late entry" missing.

#### B2. Modification audit trail (lines 16–17)

- **Applies:** all.
- **Verdict:** **always `manual_review`** — PDFs do not preserve
  in-place modifications. Flag for chart-level audit and explain in
  report.

### C. Medical and medication

#### C1. Allergies, adverse reactions, medical conditions (lines 18–19)

- **Applies:** Intake (required); Progress and Discharge (conditional,
  if meds discussed).
- **Rule path:** look for `Allergies:` and `Medical History:`
  sections. Absence in an Intake → `fail`. Presence of `NKDA`, `none`,
  `none reported` counts as the required "prominent note of no
  relevant history".
- **Judge path:** LLM confirms the negation is prominent (not buried in
  a 200-word paragraph).

#### C2. Medication tracking (lines 20–29)

Five sub-items, all conditional on the note touching medications:

- **C2a — order types (standing/PRN/STAT) for all Rx and OTC:** rule path
  parses a `Medications:` section and checks each entry has an order
  type label.
- **C2b — date, dosage, frequency per medication:** rule path enforces
  the regex `[\w\-]+\s+\d+\s*mg.*\bq\.?d\.?|bid|tid|qid|prn`-style
  schedule plus a date.
- **C2c — informed consent:** rule searches for `informed consent`
  language or a consent form reference. LLM judge confirms the four
  required elements (benefits, risks, side effects, alternatives) are
  addressed.
- **C2d — change rationale or no-change rationale:** LLM judge over
  the meds section.
- **C2e — discharge med list:** rule check on Discharge Summary that a
  `Medications at Discharge:` section exists and lists doses.

### D. Assessment content (Intake notes)

#### D1. Presenting problems, MSE, psychosocial conditions, source (lines 30–32)

- **Rule path:** require sections titled `Presenting Problem(s):`,
  `Mental Status Exam:` (or `MSE:`), `Psychosocial History:` /
  `Social History:`. Each must be non-empty.
- **Judge path:** LLM scores adequacy. Specifically asks: does the MSE
  cover the standard MSE dimensions (appearance, behaviour, speech,
  mood, affect, thought process, thought content, perception,
  cognition, insight, judgment)? Does the presenting problem
  identify the source (member self-report, collateral, referring
  provider)?

#### D2. Special status assessment (lines 33–35)

- **Applies:** Intake (required); Progress and Consult (conditional).
- **Rule path:** for each of {suicidal ideation, homicidal ideation,
  self-injurious behaviour, elopement risk, imminent risk of harm},
  search for either an explicit assessment or an explicit denial. The
  standard requires both presence-or-absence statements — silence is a
  `fail`.
- **Judge path:** LLM extracts which categories are addressed.

#### D3. Medical and psychiatric history (lines 36–38)

- **Rule path:** look for `Past Psychiatric History:` and `Past Medical
  History:` sections; require at least one of: previous treatment
  dates, prior clinician/facility names, prior interventions and
  responses, sources, family history.
- **Judge path:** LLM scores coverage of the five elements.

#### D4. Behavioral health history — history of abuse (lines 39–40)

- **Rule path:** require explicit assessment of trauma/abuse history
  (presence or denial). Keywords: `trauma history`, `abuse history`,
  `history of abuse`, plus `denies` / `reports`.
- **Judge path:** LLM disambiguates references.

#### D5. Adolescent sexual behavior history (line 41)

- **Applies:** member age 12–17 (need DOB; see Q-DEMO-2).
- **Rule path:** look for a `Sexual History:` or
  `Sexual Behavior History:` section.
- **Judge path:** if free-text, LLM confirms presence.

#### D6. Child/adolescent prenatal, perinatal, developmental history (lines 42–44)

- **Applies:** member age < 18.
- **Rule path:** require coverage of (a) prenatal/perinatal events,
  (b) developmental — physical, psychological, social, intellectual,
  academic. Section title `Developmental History:` is the anchor.
- **Judge path:** LLM scores per dimension.

#### D7. 12+ substance use (lines 45–46)

- **Applies:** member age ≥ 12.
- **Rule path:** require a `Substance Use History:` section addressing
  nicotine, alcohol, illicit drugs, Rx, OTC. Each can be present or
  explicitly denied.
- **Judge path:** LLM checks coverage of all five substance
  categories.

#### D8. DSM diagnosis consistent with assessment (lines 47–48)

- **Rule path:** extract the diagnosis section. Confirm DSM code
  format.
- **Judge path:** **LLM-required.** Compare diagnosis against
  presenting-problem, history, MSE, and assessment sections. Verdict
  asks whether the diagnosis is **supported** by the assessment, not
  whether it is correct.

#### D9. Medical/psychosocial/environmental factors and functional impairment (lines 49–51)

- **Rule path:** look for `Functional Impairment:` or
  `Impact on Functioning:` sections.
- **Judge path:** LLM confirms the section addresses functional
  impact, not just diagnosis.

### E. Treatment plan elements

#### E1. Specific symptoms and problems tied to diagnosis (line 54)

- **Rule path:** the plan must include a `Problems:` or
  `Target Symptoms:` section. Each problem listed.
- **Judge path:** LLM confirms each listed problem maps to a
  diagnostic symptom (no orphan problems).

#### E2. Prioritisation; deferred problems noted (lines 55–56)

- **Rule path:** problems must be ordered or numbered, with deferred
  items labelled `deferred`.
- **Judge path:** LLM confirms prioritisation is explicit.

#### E3. Recommended level of care relates to impairment (line 57)

- **Rule path:** plan must state the LOC (`Outpatient`, `IOP`, …) and
  reference impairment.
- **Judge path:** LLM confirms the rationale ties LOC to impairment.

#### E4. Member (and family) involvement in planning (line 58)

- **Rule path:** look for `Member Involvement:` or sentences with
  `member participated`, `member agrees`, signature blocks.
- **Judge path:** LLM confirms collaborative planning is documented.

#### E5. SMART goals — specific, behavioural, measurable, realistic (line 59)

- **Rule path:** goals must use measurable language (`will reduce X by
  Y%`, frequency words, scales). Heuristic.
- **Judge path:** **LLM-required.** Per goal, score on each SMART
  dimension. Aggregate.

#### E6. Goal time frame (line 60)

- **Rule path:** each goal must have a target date or duration phrase
  (`by [date]`, `within N weeks`).
- **Judge path:** LLM confirms presence.

#### E7. Progress or lack of progress toward goals (line 61)

- **Applies:** treatment plan updates (revisions).
- **Rule path:** updated plans must include a `Progress:` annotation
  per goal.
- **Judge path:** LLM scores adequacy.

#### E8. Rationale for estimated treatment length (line 62)

- **Rule path:** plan must include `Length of Treatment:` or
  `Estimated Duration:` with text.
- **Judge path:** LLM confirms rationale, not just a number.

#### E9. Updates on goal achievement / new problems (line 63)

- **Applies:** treatment plan updates.
- **Rule path:** check for revision metadata and dated entries.
- **Judge path:** LLM confirms updates reflect new state.

#### E10. Re-evaluation when progress stalls (line 64)

- **Rule path:** when E7 indicates lack of progress, plan must contain
  modified goals or interventions.
- **Judge path:** LLM confirms modification is responsive to
  stagnation.

### F. Progress note elements

#### F1. Signature (line 66)

- **Rule path:** signature block at end of note, matching clinician
  name and credential. Already partially extracted in
  `_extract_license_id`.
- **Judge path:** none.

#### F2. Date of service (line 67)

- **Rule path:** present in header (`Date and Time:`); already
  extracted.

#### F3. Telehealth documentation (line 68)

- **Applies:** any note where telehealth was used.
- **Rule path:** if `Location:` indicates remote, or
  `Service Code` is a telehealth modifier (95 / GT / 02 POS), the body
  must reference `telehealth`, `video`, or equivalent.
- **Judge path:** LLM confirms a telehealth statement appears (some
  EHRs use modifier 93 for audio-only).

#### F4. Member strengths and limitations toward goals (line 69)

- **Rule path:** require `Strengths:` and `Limitations:` (or
  `Barriers:`) sub-sections.
- **Judge path:** LLM confirms substance.

#### F5. Interventions consistent with treatment-plan goals (lines 70–71)

- **Rule path:** progress note must reference at least one
  intervention, and (when an associated treatment plan is in scope)
  that intervention must align with a goal/objective.
- **Judge path:** **LLM-required** when the treatment plan is
  available. Otherwise `manual_review`.

#### F6. Follow-up dates (line 72)

- **Rule path:** look for `Next Appointment:|Follow-up:`.
- **Judge path:** none.

#### F7. Missed appointments + outreach (line 73)

- **Applies:** progress notes for sessions that did not occur.
- **Rule path:** notes with `No Show:|Missed Appointment:|Cancelled:`
  must document the outreach attempt (`called`, `texted`,
  `voicemail`).
- **Judge path:** LLM confirms outreach.

#### F8. Time-based duration (line 74)

- **Rule path:** for time-based service codes (90832/4/7), the note
  must include `Duration:` or `Start:`/`End:` times.

### G. Discharge planning (concurrent, from intake)

#### G1. Ongoing discharge planning (lines 75–79)

- **Applies:** Intake (required at initiation), treatment plan
  (required), progress (conditional — major-change notes).
- **Sub-items checked:** discharge criteria, barriers + interventions,
  support systems (or lack thereof).
- **Rule path:** look for `Discharge Plan:|Discharge Criteria:|
  Support Systems:|Barriers:` sections.
- **Judge path:** LLM confirms all three sub-items addressed.

### H. Discharge summary

#### H1. Reason for treatment episode (line 82)

- **Rule path:** require `Reason for Treatment:|Episode Summary:`
  section.

#### H2. Goals achieved or reasons not achieved (line 83)

- **Rule path:** structured goal review.
- **Judge path:** LLM confirms each plan goal is addressed.

#### H3. Specific follow-up / aftercare (line 84)

- **Rule path:** require `Aftercare Plan:` with specific referrals,
  appointments, or self-care steps.
- **Judge path:** LLM confirms specificity (not "follow up as needed").

### I. Coordination of care

#### I1. Documented coordination, including refusal (lines 85–87)

- **Applies:** Intake, Consultation, Discharge (required); Progress
  (conditional, when external contact occurred).
- **Rule path:** look for `Coordination of Care:|Release of
  Information:|Communication with:` sections. If member refused, the
  note must contain refusal + reason.
- **Judge path:** LLM disambiguates.

#### I2. Coordination at key milestones (lines 88–93)

- **Applies:** intake (at intake), discharge (at discharge),
  consultation (level-of-care transitions).
- **Rule path:** verify the milestone-appropriate coordination note
  exists.

### J. Referrals

#### J1. Referrals to clinicians, services, community resources, wellness/prevention programs (lines 94–95)

- **Applies:** any note where the clinician identifies an unmet need.
- **Rule path:** look for `Referrals:|Referred to:|Recommended:` plus a
  target.
- **Judge path:** LLM confirms substance.

### K. Telehealth

#### K1. Telehealth noted in record (lines 98–99)

- Same as F3; surfaces independently in the report under telehealth.

#### K2. State-specific telehealth requirements (line 100)

- **Verdict:** **always `manual_review`** — outside the tool's scope.
  The report flags this for the supervisor.

## 5. System architecture

The engine is a Python package, `compliance/`, with the following modules.
Each module corresponds to one well-defined responsibility:

```
compliance/
├── __init__.py
├── ingest.py            # PDF → list[Note]; splits multi-note PDFs
├── classify.py          # Note → DocumentType
├── extract/             # field extractors (rule-based, deterministic)
│   ├── header.py        # date, clinician, member, duration, location, service code
│   ├── sections.py      # locate named sections in body text
│   ├── medications.py   # parse Meds section
│   └── signature.py     # signature block + license
├── checks/              # one check per standard item
│   ├── base.py          # Check protocol; CheckResult dataclass
│   ├── a_identification.py
│   ├── b_entry.py
│   ├── c_medication.py
│   ├── d_assessment.py
│   ├── e_treatment_plan.py
│   ├── f_progress.py
│   ├── g_discharge_planning.py
│   ├── h_discharge_summary.py
│   ├── i_coordination.py
│   ├── j_referrals.py
│   └── k_telehealth.py
├── judges/              # pluggable LLM judges
│   ├── base.py          # Judge protocol
│   ├── null.py          # default: returns "manual_review" without calling an LLM
│   ├── claude.py        # Anthropic API judge (deferred decision; see Q-LLM-1)
│   └── local.py         # local-model judge (deferred)
├── applicability.py     # matrix from §3, as data
├── runner.py            # orchestrates: ingest → classify → checks → results
└── report/
    ├── json_writer.py
    ├── csv_writer.py
    └── html_writer.py    # per-note HTML with highlighted excerpts
```

### Engine contract

```python
# compliance/checks/base.py

from typing import Protocol, Literal
from dataclasses import dataclass

Verdict = Literal["pass", "fail", "not_applicable", "manual_review"]

@dataclass(frozen=True)
class CheckResult:
    standard_id: str             # e.g. "A3.duration"
    verdict: Verdict
    rationale: str               # short human-readable explanation
    excerpts: list[str]          # supporting text from the note
    page_numbers: list[int]      # source pages
    judge_used: str | None       # None for rule-only, else judge name

class Check(Protocol):
    standard_id: str
    applies_to: frozenset[str]    # DocumentType values

    def run(self, note: "Note", judge: "Judge") -> CheckResult: ...
```

### Judge contract

```python
# compliance/judges/base.py

class Judge(Protocol):
    name: str
    def evaluate(self, *, question: str, context: str, schema: type) -> "JudgeAnswer": ...
```

`NullJudge` always returns `manual_review` — this is what ships in V1 so
the system runs end-to-end without an LLM dependency. `ClaudeJudge` and
`LocalJudge` are interchangeable implementations introduced later.

### Runner flow

```
PDF batch
  ↓  ingest.split_notes()           # per-note objects with pages + text
  ↓  classify.assign_type()         # uses note-type header + service code
  ↓  for each note:
       extractors fill structured fields
       for each Check whose applies_to includes the note's type:
         result = check.run(note, judge)
       results aggregated as NoteReport
  ↓  reporters emit JSON / CSV / HTML
```

## 6. Data model

```python
@dataclass
class Page:
    index: int                    # 0-based within source PDF
    text: str
    page_num_in_note: int         # from "Page X of Y"
    page_total_in_note: int

@dataclass
class Note:
    source_pdf: Path
    page_indices: list[int]       # pages from the source PDF making up this note
    pages: list[Page]
    note_type: DocumentType
    header: HeaderFields          # date, clinician, member, duration, location, service_code
    sections: dict[str, str]      # section_name → body text (lowercased keys)
    full_text: str

@dataclass
class HeaderFields:
    service_date: date | None
    duration_minutes: int | None
    start_time: time | None
    end_time: time | None
    clinician: str | None
    clinician_credential: str | None
    license_state: str | None
    license_id: str | None
    member_name: str | None
    member_id: str | None
    member_dob: date | None       # if available
    location: str | None
    service_code: str | None
    participants: list[str]

@dataclass
class NoteReport:
    note: Note
    results: list[CheckResult]
    @property
    def pass_rate(self) -> float: ...
    @property
    def failures(self) -> list[CheckResult]: ...
```

Persistence: results write to `findings.jsonl` (one line per
`CheckResult`) so downstream tooling can `jq`/SQL aggregate without
re-parsing nested JSON.

**Cross-note context.** Checks like F5 (interventions ↔ goals) and E7 /
E9 / E10 (plan updates) need access to more than one note. The runner
will pass an optional `ContextBundle` of related notes (same member,
same episode) to such checks. The bundle's concrete type is left TBD
until Q-MEMBER-1 is resolved — without a stable member/episode key we
cannot build it correctly. Single-note checks ignore the bundle.

## 7. Implementation phases

### Phase 0 — Refactor existing code (1 week)

- Extract the header/regex logic from `scanner.py` and `fixtnpdf.py` into
  `compliance/extract/header.py`. Both legacy scripts import from the new
  module.
- Build the `Note` / `Page` data model.
- Build `ingest.split_notes()` using `Page X of Y` boundaries.
- Build `classify.assign_type()` from the existing `RE_NOTE_TYPE` and
  service-code rules.

**Exit criteria:** `scanner.py` works unchanged from the user's view.

### Phase 1 — Section extractor + applicability matrix (1 week)

- `extract/sections.py` — find canonical section headers; emit a
  normalised section dict.
- `applicability.py` from the §3 matrix.
- `runner.py` skeleton that iterates checks against notes (with no
  checks implemented yet).

### Phase 2 — Rule-based checks (3 weeks)

Implement every standard from §4 where the rule path is sufficient on
its own. Each check has unit tests against synthetic and real notes.

Order of implementation (by tractability):

1. A1, A3, B1, F1, F2, F6, F8 — extractable, deterministic.
2. A4, A5, F3, F7, K1 — conditional but rule-only.
3. C1, C2a, C2b, C2e — meds, mostly rules.
4. D2, D3, D4, D7 — section-presence and keyword.
5. G1 sub-items, H1, H2, H3 — section-presence on discharge / plan.
6. I1, I2, J1 — coordination/referral sections.
7. E1, E2, E3, E6, E8 — treatment-plan structural items.

**Exit criteria:** the engine runs end-to-end with `NullJudge`,
producing CSV + JSON + HTML reports against the sample
`sourcedocs/` PDF.

### Phase 3 — Judge-required checks via NullJudge (1 week)

Wire up the checks that depend on a judge (D1, D5, D6, D8, D9, E4, E5,
E7, E9, E10, F4, F5, C2c, C2d). They all return `manual_review` until a
real judge is plugged in, but the runner, reporter, and matrix are
exercised.

### Phase 4 — Real judges (3+ weeks, gated on Q-LLM-1)

Two parallel tracks:

- **ClaudeJudge:** prompt templates per check, structured-output parsing
  via Anthropic SDK with prompt caching for the standard-text
  reference.
- **LocalJudge:** swap in a local LLM (Ollama). Same prompt templates,
  smaller models.

Each judge ships with regression tests against an annotated corpus of
known-good and known-bad notes.

### Phase 5 — Front-ends (parallelisable)

- CLI: `python -m compliance audit --input sourcedocs/ --output reports/`
- Real-time single-note endpoint (FastAPI service): POST a PDF, get
  JSON findings.
- Aggregate dashboard: SQLite-backed; static HTML rendered from
  `findings.jsonl`.

## 8. Project report — what was planned for

**At a glance:**

- The plan converts the `fixtnpdf` codebase into a compliance audit
  engine that grades clinical notes against every numbered standard in
  `Record Standards.txt`. The existing PDF ingestion and field
  extraction is reused; the new layers are document classification,
  section extraction, a check registry, a pluggable judge interface,
  and a reporting layer.
- **Coverage.** Every line of `Record Standards.txt` is mapped to one
  or more checks in §4 (items A1–K2). Items that cannot be assessed
  from PDFs alone (B2 modification audit trail, K2 state-specific
  telehealth law) are explicitly handed off as `manual_review` rather
  than ignored, so audit completeness is preserved.
- **Document types.** Intake, Treatment Plan, Progress Note,
  Consultation Note, and Discharge Summary are first-class. Group and
  family session notes are handled as variants of Progress with their
  own A4 / A5 checks. The applicability matrix in §3 is the contract:
  every Check declares the types it runs against.
- **Phased delivery.** Phase 0–2 produce a working rules-only engine
  against the sample sourcedocs in ~5 weeks. Phase 3 wires in the
  pluggable-judge architecture without any LLM dependency. Phase 4
  layers real LLM judges (Claude or local) on top — the decision is
  deferred per the user's preference but the interface is built in
  Phase 3 so adding a judge does not require re-architecture.
- **Outputs.** Per-note JSON (`findings.jsonl`), per-batch CSV (a
  finding per row, suitable for spreadsheet/SQL roll-up), and per-note
  HTML reports with highlighted excerpts of each failing or
  judge-pending finding. The HTML report also surfaces the standard
  text verbatim alongside the finding so a clinician reviewing their
  own note can see exactly which standard fired.
- **Use-case fit.**
  - *Internal QA* runs Phase 2's CLI over a directory and reads the CSV/HTML.
  - *Aggregate reporting* reads `findings.jsonl` into the dashboard.
  - *Real-time clinician feedback* hits the Phase 5 service endpoint.
  All three share the same engine and check definitions.
- **What is out of scope.** Cross-chart context (verifying that a
  consent form on file is current, longitudinal medication
  reconciliation), modification audit-trail detection, and state-law
  telehealth nuances. These are flagged in the report as
  `manual_review` items so the supervisor knows the audit is not
  silently incomplete.

## 9. Technical challenges

1. **Section detection is brittle in EHR-generated PDFs.** Section
   headers vary by EHR template (`Presenting Problem:` vs
   `Reason for Visit:` vs `Chief Complaint:`). The rule path needs a
   per-EHR header synonym table. Sample PDFs from every EHR template
   in use must be collected before §4 sections are finalised. (See
   Q-EHR-1.)

2. **`dummylink` overlap noted in CLAUDE.md.** The known
   `D diuamgnmoysliisnk` corruption affects section-header matching
   because the corrupted page can scramble the very word a header
   regex would have anchored on. The `extract/sections.py` module must
   defuse this: strip the `dummylink` artifact before matching, then
   restore offsets so excerpts in the report still point to real page
   text.

3. **Multi-note PDFs.** `Page X of Y` is the boundary signal per
   CLAUDE.md, but PDFs may contain notes of different types in any
   order. Classification must run per note, not per file, and must be
   robust to a "Note Type" header that occasionally wraps or appears
   on page 2 due to template glitches.

4. **Distinguishing presence-vs-quality.** Many standards conflate the
   two: "MSE results" is satisfied by an MSE section, but "a
   *meaningful* MSE" is the actual standard. Rules can only test the
   first; we need an explicit boundary in the report ("rule-only
   pass — content not assessed") so that a Phase-2 pass is not
   misread as a Phase-4 pass.

5. **LLM judge reproducibility and PHI handling.** A Claude-API judge
   sends PHI off-machine. A local judge keeps PHI on-machine but with
   weaker reasoning. The judge interface is built so a single check
   can be re-evaluated by both and the two verdicts compared. (See
   Q-LLM-1, Q-PHI-1.)

6. **Diagnosis-to-assessment alignment (D8) and intervention-to-goal
   alignment (F5).** These are cross-section reasoning problems. The
   rule path is insufficient; the judge path is required, and the
   judge needs access to both sections at once. The runner must
   support checks that consume *multiple* sections (or even multiple
   notes) — F5 specifically needs the progress note and the
   corresponding treatment plan. The data model already allows this
   (Notes are addressable; the runner can pass a "context bundle")
   but cross-note checks require us to associate notes to the same
   member and episode — non-trivial when the only key is the
   `Patient:` field text (see Q-MEMBER-1).

7. **Conditional standards depend on member age.** D5 (12+ sexual
   history), D6 (<18 developmental), D7 (12+ substance use) require
   DOB. DOB is in some intake templates but not always extractable
   reliably. We need a degraded-mode behaviour: if age is unknown, the
   check returns `manual_review` rather than silently skipping.

8. **Telehealth detection by service code is incomplete.** Telehealth
   modifiers vary (95, GT, GQ, POS 02, POS 10, modifier 93 for
   audio-only). The rule needs a maintained code/modifier table; new
   payor rules emerge each year (see Q-EHR-2).

9. **Late-entry detection requires an entry date.** Not every EHR
   stamps an entry date inside the PDF body. Some carry it as PDF
   metadata (`/CreationDate`). The extractor needs to attempt body
   text → PDF metadata → file mtime in that order, and B1 must mark
   `manual_review` when only the latter is available, since file mtime
   is unreliable.

10. **Report performance and noise.** A 50-check matrix run over a
    100-note batch yields ~5000 findings, of which most will be
    `not_applicable` (matrix-filtered). The CSV/HTML must default to
    showing only `fail` and `manual_review`, with a flag to include
    full results, or supervisors will tune out.

## 10. Open questions

Each question has an ID we can reference in the code and in
follow-ups.

**Inputs and scope**

- **Q-INPUTS-1.** Are demographic and consent records (standard A2)
  ever present in the encounter-note PDFs, or do they live elsewhere
  in the EHR? If only elsewhere, A2 is `manual_review` for every note
  type. Confirmed-by-user that the V1 tool sees only the PDF batch —
  but is the expectation that A2 still shows up in audit reports as a
  flagged item, or should we suppress it for V1?
- **Q-INPUTS-2.** Will the input batch ever include attached forms
  (e.g. consent PDFs concatenated into the note PDF)? If yes, we need
  per-page classification, not just per-note.
- **Q-INPUTS-3.** How big is a typical batch (notes/day, notes/week)?
  This shapes whether `findings.jsonl` can stay flat or whether we
  need SQLite from day one.

**EHR template variance**

- **Q-EHR-1.** Is every PDF produced by a single EHR template, or do
  we have multiple sources? If multiple, can you provide one sample
  PDF per template so the section-synonym table in
  `extract/sections.py` is comprehensive?
- **Q-EHR-2.** Which CPT codes and modifiers does your billing
  configuration use for telehealth? (We will hard-code an initial
  table; need yours.)
- **Q-EHR-3.** Does the EHR ever embed entry date in body text, or do
  we have to fall back to PDF `/CreationDate`?

**Member identity**

- **Q-MEMBER-1.** Is the `Patient:` field's text the canonical member
  identifier, or is there a numeric MRN that we should prefer? Cross-
  note checks (F5 needs progress + plan together) depend on a stable
  key.
- **Q-DEMO-1.** Guardianship is only required for minors / dependent
  adults. How is the EHR signalling dependent-adult status? (Otherwise
  we cannot distinguish "guardianship missing because not required"
  from "guardianship missing in error".)
- **Q-DEMO-2.** Is the member's date of birth reliably present in
  intake notes? If not, age-dependent checks (D5, D6, D7) default to
  `manual_review`.

**LLM judges**

- **Q-LLM-1.** When we move past rules-only, do you want the Claude API
  path, the local-model path, or both? PHI handling drives this. The
  plan keeps both options open; we need a decision before Phase 4
  begins.
- **Q-LLM-2.** Is a BAA in place with Anthropic if we use the Claude
  API on PHI? If not, the local-model path is the only legal option
  for Phase 4.
- **Q-LLM-3.** Where is the LLM-judge corpus (annotated good/bad
  notes) going to come from? Without an evaluation set we cannot
  measure judge regressions over time.

**Standards interpretation**

- **Q-STD-1.** Standard A1 says "name or ID on each page." The
  source PDFs we have do not put the member identifier on every page
  (e.g. signature-only last pages). Is the standard's intent
  satisfied by a single appearance per note, or is per-page literal?
- **Q-STD-2.** Standard B1 ("late entry") requires the literal phrase
  or just the equivalent meaning? We default to the literal phrase —
  please confirm.
- **Q-STD-3.** Standard E5 (SMART goals) — for a goal that is
  partially SMART (e.g. specific + measurable but not time-bound), do
  you want one finding per missing dimension, or one aggregate
  finding per goal?
- **Q-STD-4.** For standard K2 (state-specific telehealth), should
  we (a) list the standard as `manual_review` once per note, or (b)
  attempt to detect the state of practice from the license number and
  surface a state-specific reading list? (b) is plausible but
  out-of-scope for V1.

**Operational**

- **Q-OPS-1.** Who is the audience for the per-note HTML report —
  the clinician who wrote the note, or a QA reviewer? The wording
  changes substantially.
- **Q-OPS-2.** Should `compliance/checks/*` be data-driven from a
  YAML config (so non-developers can edit thresholds and section
  synonyms) or stay as code? The code path is faster to build; the
  YAML path scales better as the standards corpus grows.
- **Q-OPS-3.** Do we need a CSV/JSON contract with any external
  system (e.g. dashboard pipeline, regulator submission)? If so, the
  schema in §6 is provisional and must be reviewed against that
  contract.
