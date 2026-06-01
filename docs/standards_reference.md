# Standards Reference — notecompliance

Each section below covers one standard: the payer's verbatim requirement,
which document types it applies to, and exactly how the engine decides
pass, fail, not-applicable, or manual-review.

**Verdict meanings**

| Verdict | Meaning |
|---|---|
| **PASS** | The rule found what it needed. |
| **FAIL** | Something required was missing or wrong. |
| **REVIEW** | The rule cannot decide; a human (or AI judge) must evaluate. |
| **N/A** | This standard does not apply to the note's document type. |
| **SKIPPED** | AI judging is disabled (`--no-ai`); judgment-required checks were not run. |

---

## Table of Contents

**A — Identification and encounter metadata**
- [A1 — Member ID on each page](#a1--member-id-on-each-page)
- [A2 — Demographics, contacts, consent](#a2--demographics-contacts-consent)
- [A3 — Encounter metadata](#a3--encounter-metadata)
- [A4 — Group session subject](#a4--group-session-subject)
- [A5 — Family session attendees](#a5--family-session-attendees)

**B — Entry integrity**
- [B1 — Late entry notation](#b1--late-entry-notation)
- [B2 — Modification audit trail](#b2--modification-audit-trail)

**C — Medical and medication**
- [C1 — Allergies and medical conditions](#c1--allergies-and-medical-conditions)
- [C2a — Medication order types](#c2a--medication-order-types)
- [C2b — Medication date, dose, and frequency](#c2b--medication-date-dose-and-frequency)
- [C2c — Medication informed consent](#c2c--medication-informed-consent)
- [C2d — Medication change rationale](#c2d--medication-change-rationale)
- [C2e — Discharge medication list](#c2e--discharge-medication-list)

**D — Assessment content (intake notes)**
- [D1 — Presenting problem, MSE, psychosocial, source](#d1--presenting-problem-mse-psychosocial-source)
- [D2 — Special status assessment](#d2--special-status-assessment)
- [D3 — Medical and psychiatric history](#d3--medical-and-psychiatric-history)
- [D4 — Abuse and trauma history](#d4--abuse-and-trauma-history)
- [D5 — Adolescent sexual behavior history](#d5--adolescent-sexual-behavior-history)
- [D6 — Child/adolescent developmental history](#d6--childadolescent-developmental-history)
- [D7 — Substance use history](#d7--substance-use-history)
- [D8 — DSM diagnosis consistent with assessment](#d8--dsm-diagnosis-consistent-with-assessment)
- [D9 — Functional impairment documentation](#d9--functional-impairment-documentation)

**E — Treatment plan elements**
- [E1 — Symptoms/problems tied to diagnosis](#e1--symptomsproblems-tied-to-diagnosis)
- [E2 — Problem prioritization](#e2--problem-prioritization)
- [E3 — Level of care rationale](#e3--level-of-care-rationale)
- [E4 — Member involvement in planning](#e4--member-involvement-in-planning)
- [E5 — SMART goals](#e5--smart-goals)
- [E6 — Goal time frames](#e6--goal-time-frames)
- [E7 — Progress toward goals](#e7--progress-toward-goals)
- [E8 — Rationale for treatment length](#e8--rationale-for-treatment-length)
- [E9 — Goal updates on revision](#e9--goal-updates-on-revision)
- [E10 — Re-evaluation when progress stalls](#e10--re-evaluation-when-progress-stalls)

**F — Progress note elements**
- [F1 — Clinician signature](#f1--clinician-signature)
- [F2 — Date of service](#f2--date-of-service)
- [F3 — Telehealth documentation](#f3--telehealth-documentation)
- [F4 — Member strengths and limitations](#f4--member-strengths-and-limitations)
- [F5 — Interventions consistent with goals](#f5--interventions-consistent-with-goals)
- [F6 — Follow-up dates](#f6--follow-up-dates)
- [F7 — Missed appointment outreach](#f7--missed-appointment-outreach)
- [F8 — Time-based duration](#f8--time-based-duration)

**G — Discharge planning**
- [G1 — Ongoing discharge planning](#g1--ongoing-discharge-planning)

**H — Discharge summary**
- [H1 — Reason for treatment episode](#h1--reason-for-treatment-episode)
- [H2 — Goals achieved or not achieved](#h2--goals-achieved-or-not-achieved)
- [H3 — Specific aftercare plan](#h3--specific-aftercare-plan)

**I — Coordination of care**
- [I1 — Coordination of care documented](#i1--coordination-of-care-documented)
- [I2 — Coordination at key milestones](#i2--coordination-at-key-milestones)

**J — Referrals**
- [J1 — Referrals to services and resources](#j1--referrals-to-services-and-resources)

**K — Telehealth**
- [K1 — Telehealth noted in record](#k1--telehealth-noted-in-record)
- [K2 — State-specific telehealth requirements](#k2--state-specific-telehealth-requirements)

---

## A — Identification and encounter metadata

### A1 — Member ID on each page

**Applies to:** all document types (required)

**Payer requirement:** The member's name or identification number on each page of the record.

This standard ensures that every page of a clinical record can be traced back to the correct member, which is essential for chart integrity during audits. The rule extracts the member name from the `Patient:` header field on the first page and then checks whether that name appears somewhere in the text of every subsequent page. Because the EHR generates the name in the running header, it should appear on every page; pages that lack it — typically signature-only last pages in some templates — are flagged individually.

**Pass rule:** The member name extracted from the header is found (case-insensitive) in the text of every page in the note.

**Fail rule:** One or more pages do not contain the member name. The rationale lists the specific page numbers that are missing it.

**Edge case:** If the member name cannot be extracted from the header at all, the check fails with the rationale "Member name not extractable from note header."

---

### A2 — Demographics, contacts, consent

**Applies to:** intake notes (required)

**Payer requirement:** The member's address; employer or school; home and work telephone numbers, including emergency contacts; marital or legal status; appropriate consent forms; and guardianship information.

Intake notes are the foundation of the member record and must contain basic identifying and contact information so the treating facility can reach the member or their contacts in an emergency. The rule looks for five canonical section headers in the note body: address, phone/contact numbers, emergency contact, marital/legal status, and consent form.

**Pass rule:** All five sections are present and non-empty.

**Fail rule:** One or more sections are missing. The rationale lists which sub-items were not found.

**Note:** Guardianship is not in the hard-fail list; it is captured in the section synonym table but not independently required by the rule (only required when the member is a minor or dependent adult — information the engine cannot always determine from the PDF alone).

---

### A3 — Encounter metadata

**Applies to:** intake, progress, consultation, discharge, group, family notes (required)

**Payer requirement:** The date of service, either start and stop time or total time in session (for time-based services), notation of session attendees, diagnosis, services rendered, the rendering clinician's name, professional degree, license and relevant identification number as applicable.

Every encounter note must contain enough structured data to confirm the service occurred, who provided it, who received it, what was billed, and under what diagnosis. The rule checks eight individual sub-items, each extracted from the note header: date of service, duration (total minutes or start/stop times), participants, diagnosis (a named section or a DSM/ICD code pattern in the full text), service code, clinician name, clinician credential, and license ID.

**Pass rule:** All eight sub-items are present.

**Fail rule:** Any sub-item is missing. The rationale lists everything that was not found.

---

### A4 — Group session subject

**Applies to:** progress notes with a group CPT code (90853, 90849, 90857) or note type "group" (required for those; conditional for plain progress notes)

**Payer requirement:** For group sessions, the subject covered in the session on the date of service must be indicated.

A group therapy note must document what the group actually discussed so that the payer can verify clinical content was delivered, not just attendance. The rule first looks for a named "Topic", "Subject", or "Session Focus" section. If none is found, the check falls through to the AI judge, which reads the note body and decides whether a group topic is implied in the narrative.

**Pass rule (rule path):** A recognized topic section is present and non-empty.

**Pass/fail/review (judge path):** The AI judge answers whether the note body identifies a session topic. Returns `manual_review` under NullJudge or `--no-ai`.

**Not-applicable:** The note is not flagged as a group session (neither note type nor CPT code indicates group therapy).

---

### A5 — Family session attendees

**Applies to:** progress notes with a family CPT code (90847, 90846, 90849) or note type "family" (required for those; conditional for plain progress notes)

**Payer requirement:** For family sessions, list everyone who attended the session and relationship to each other.

Family therapy records must identify all participants by name and their relationship to one another so the payer can verify who was part of the session. The rule checks the `Participants:` header field and any "participants" section for at least two named people plus a relationship word (mother, father, spouse, partner, sibling, guardian, etc.).

**Pass rule (rule path):** At least two participants are listed and at least one relationship term is found.

**Pass/fail/review (judge path):** If the rule path doesn't find enough structure, the AI judge reads the participants text and decides. Returns `manual_review` under NullJudge or `--no-ai`.

**Not-applicable:** The note is not a family session.

---

## B — Entry integrity

### B1 — Late entry notation

**Applies to:** all document types (conditional — only active when entry date is more than 24 hours after service date)

**Payer requirement:** If an entry is made more than 24 hours after the service was rendered, the entry should include the date of service, date of the entry and a notation that it is a late entry.

Timely documentation is a clinical and legal standard. When a note is entered late, the record must acknowledge this so reviewers know when the service occurred versus when it was documented. The rule extracts the service date from the `Date and Time:` header and the entry/signing date from fields like `Entry Date:`, `Note Created:`, or `Signed on:`. It then computes the gap.

**Not-applicable:** The gap between service date and entry date is 24 hours or less (the threshold is configurable in `rules/thresholds.yaml` under `late_entry_hours`).

**Pass rule:** The gap exceeds the threshold AND the phrase "late entry" (case-insensitive) appears in the note text.

**Fail rule:** The gap exceeds the threshold but "late entry" is not present.

**Manual review:** The service date was found but the entry date could not be extracted from the note text (the engine cannot reliably use file modification time as a proxy).

---

### B2 — Modification audit trail

**Applies to:** all document types

**Payer requirement:** Any error is to be lined through so that it can still be read, then dated and initialed by the person making the change.

This standard requires that corrections to a clinical record are made with a dated, initialed line-through rather than erasure or overwriting. PDFs do not preserve the editing history of the original EHR entry, so the engine cannot detect whether corrections were made correctly or at all.

**Verdict:** Always `manual_review`. The rationale directs the reviewer to inspect the original EHR record for evidence of line-through corrections. This is intentional — the engine signals that the standard exists and must be checked, rather than silently skipping it.

---

## C — Medical and medication

### C1 — Allergies and medical conditions

**Applies to:** intake and discharge notes (required); progress notes (conditional — only when medications are discussed)

**Payer requirement:** Clear documentation of medication allergies, adverse reactions and relevant medical conditions. If the member has no relevant medical history, this should be prominently noted.

Every intake and discharge note must document what the member is allergic to and any relevant medical conditions, because these directly affect medication safety and care coordination. Stating "no known allergies" (NKDA) or "none reported" explicitly satisfies the requirement — the key is that the clinician actively addressed the question rather than leaving it blank. For progress notes, the check only activates when the note body mentions medications.

**Pass rule:** Both an allergies section and a medical history section are present and non-empty (including explicit negations like NKDA, "none", or "no known allergies").

**Fail rule (intake/discharge):** Either section is missing entirely.

**Manual review (progress):** Medication is discussed but one or both sections are missing — the reviewer determines whether the omission is clinically significant.

---

### C2a — Medication order types

**Applies to:** intake, progress, discharge notes (conditional — only when a Medications section is present or medications are discussed)

**Payer requirement:** Standing, as needed (PRN) and immediate (STAT) orders for all prescription and over-the-counter medications.

Each medication listed must be tagged with its order type so that pharmacy and clinical staff know how and when it should be administered. The rule parses each line of the Medications section and looks for the words "standing", "routine", "PRN", "as needed", "STAT", or "immediate".

**Pass rule:** Every parsed medication entry has an order-type label.

**Fail rule:** One or more entries are missing an order type. The failing lines are included as excerpts.

**Manual review:** The Medications section is present but the parser could not extract individual entries (unusual formatting).

**Not-applicable:** No Medications section and no medication-related language in the note.

---

### C2b — Medication date, dose, and frequency

**Applies to:** intake, progress, discharge notes (conditional — same trigger as C2a)

**Payer requirement:** The date medications are prescribed along with the dosage and frequency.

Dose and frequency are clinical safety requirements — the wrong dose or schedule can harm the member. The parser extracts dose (e.g., "50 mg", "2 tabs") and frequency (e.g., "daily", "BID", "PRN") from each medication line.

**Pass rule:** Every parsed entry has both a dose and a frequency.

**Fail rule:** One or more entries are missing either dose or frequency. The specific gaps are listed in the rationale.

**Manual review:** Entries could not be parsed.

---

### C2c — Medication informed consent

**Applies to:** intake, progress, discharge notes (conditional — same trigger as C2a)

**Payer requirement:** Informed member consent for medication, including the member's understanding of the potential benefits, risks, side effects and alternatives to the medications.

Informed consent for medication is both a clinical ethics requirement and a payer documentation standard. The rule scans the full note text for consent language ("informed consent", "consent for medication", "benefits…risks"). If consent language is found, the AI judge evaluates whether all four required elements — benefits, risks, side effects, and alternatives — are addressed.

**Pass/fail/review:** Determined by the AI judge when consent language is detected. Returns `manual_review` under NullJudge or `--no-ai`.

**Fail rule (rule path):** No consent language is found at all.

---

### C2d — Medication change rationale

**Applies to:** intake, progress, discharge notes (conditional — same trigger as C2a)

**Payer requirement:** Changes or rationale for lack of changes in medication and/or dosage should be clearly documented along with the clinical rationale for the changes.

When medications are discussed, the clinician must either document why a change was made or explicitly note that no change was needed and why. This is entirely a judgment call — the AI judge reads the medication section and decides whether rationale is present.

**Pass/fail/review:** Determined entirely by the AI judge. Returns `manual_review` under NullJudge or `--no-ai`.

---

### C2e — Discharge medication list

**Applies to:** discharge notes (required)

**Payer requirement:** Discharge summaries should specify all medications/dosages at the time of discharge.

A discharge medication list is a critical patient safety document — it tells the next provider and the member exactly what medications they are leaving with. The rule looks for a "Medications at Discharge" or "Discharge Medications" section and then parses each entry for a dose.

**Pass rule:** The section is present, entries can be parsed, and all entries include a dose.

**Fail rule:** The section is absent; or entries are found but some are missing doses.

**Manual review:** The section is present but entries cannot be parsed.

---

## D — Assessment content (intake notes)

### D1 — Presenting problem, MSE, psychosocial, source

**Applies to:** intake notes (required); consultation notes (conditional)

**Payer requirement:** A clear summary of presenting problems, the results of mental status exam(s), relevant psychological and social conditions affecting the member's medical and psychiatric status, and the source of such information.

The intake assessment is the clinical foundation of the treatment episode. Three distinct sections must be present: a presenting problem (why the member is seeking care), a mental status exam (objective clinical observations across standard domains like mood, affect, thought process, and judgment), and a psychosocial history. The rule checks for the presence of these sections; the AI judge then evaluates whether the MSE covers the standard dimensions and whether the presenting problem identifies its information source.

**Fail rule (rule path):** One or more of the three required sections is missing.

**Pass/fail/review (judge path):** When all three sections are present, the AI judge evaluates adequacy. Returns `manual_review` under NullJudge or `--no-ai`.

---

### D2 — Special status assessment

**Applies to:** intake notes (required); progress and consultation notes (conditional)

**Payer requirement:** Prominent documentation of special status situations — imminent risk of harm, suicidal or homicidal ideation, self-injurious behaviors, or elopement potential. It is also important to document the absence of such conditions.

Every encounter note must actively address risk, not just mention it when present. Silence is a fail — the clinician must either document the risk category or explicitly state it is absent. The rule searches the full note text (or a dedicated risk/safety section) for keywords associated with each of five categories: suicidal ideation, homicidal ideation, self-injurious behavior, elopement risk, and imminent harm.

**Pass rule:** All five categories are addressed (either by keyword presence or explicit denial).

**Fail rule:** Any category is unaddressed. The rationale lists the missing categories.

---

### D3 — Medical and psychiatric history

**Applies to:** intake notes (required)

**Payer requirement:** A medical and psychiatric history including previous treatment dates, clinician or facility identification, therapeutic interventions and responses, sources of clinical data and relevant family information.

A thorough history situates the current episode within the member's broader clinical context. The rule checks for the presence of a psychiatric history section and/or a medical history section. The AI judge then evaluates whether the content covers all five required elements: previous treatment dates, prior clinician or facility names, prior interventions and responses, information sources, and relevant family history.

**Fail rule (rule path):** Neither section is present.

**Pass/fail/review (judge path):** When at least one history section is found, the AI judge evaluates coverage. Returns `manual_review` under NullJudge or `--no-ai`.

---

### D4 — Abuse and trauma history

**Applies to:** intake notes (required)

**Payer requirement:** The behavioral health history includes an assessment of any history of abuse the member has experienced.

Trauma history is clinically essential for understanding the member's presenting problems and for safe treatment planning. The rule searches the note for explicit words associated with trauma or abuse ("trauma", "abuse", "neglect", "victim") or explicit denial language ("denies", "no history of abuse", "no trauma"). Either finding a reference or an explicit denial satisfies the standard.

**Pass rule:** Either a trauma/abuse reference or an explicit denial is found.

**Fail rule:** Neither is present — the history was not addressed at all.

---

### D5 — Adolescent sexual behavior history

**Applies to:** intake notes for members aged 12–17 (conditional on age)

**Payer requirement:** For adolescents, the assessment documents a sexual behavior history.

Sexual behavior history is developmentally appropriate and clinically relevant for adolescent members. The rule first checks the member's date of birth against the service date; if the member is between 12 and 17, it looks for a "Sexual History" or "Sexual Behavior History" section. When the section is absent, the AI judge reads the note to see if the topic is addressed in the narrative.

**Not-applicable:** Member is not in the 12–17 age range.

**Manual review:** Date of birth is not available in the note (age cannot be determined).

**Pass rule (rule path):** A sexual history section is present.

**Pass/fail/review (judge path):** When the section is absent, the AI judge evaluates whether the topic is addressed in the narrative.

---

### D6 — Child/adolescent developmental history

**Applies to:** intake notes for members under age 18 (conditional on age)

**Payer requirement:** For children and adolescents, past medical and psychiatric history should include prenatal and perinatal events, along with a complete developmental history (physical, psychological, social, intellectual and academic).

A developmental history captures events that may explain current behavioral and emotional patterns. The rule checks for a "Developmental History" section. The AI judge then evaluates whether the content covers all five required dimensions.

**Not-applicable:** Member is 18 or older.

**Manual review:** Date of birth not available.

**Fail rule (rule path):** The developmental history section is absent.

**Pass/fail/review (judge path):** When the section is present, the AI judge evaluates coverage of the five dimensions.

---

### D7 — Substance use history

**Applies to:** intake notes for members aged 12 and older (conditional on age)

**Payer requirement:** For members 12 years of age and older, documentation includes past and present use of nicotine or alcohol, as well as illicit drugs, prescribed or over-the-counter medications.

Substance use history is a required part of any comprehensive mental health assessment for members 12 and older. The rule looks for keywords associated with five substance categories — nicotine/tobacco, alcohol/ETOH, illicit drugs, prescription medications, and over-the-counter medications — in either a dedicated section or the full note text. When some categories are missing by keyword, the AI judge evaluates whether they are addressed in the narrative.

**Not-applicable:** Member is under 12.

**Manual review:** Date of birth not available.

**Pass rule (rule path):** All five categories are detected by keyword.

**Pass/fail/review (judge path):** When one or more categories are missing by keyword, the AI judge evaluates narrative coverage.

---

### D8 — DSM diagnosis consistent with assessment

**Applies to:** intake notes (required)

**Payer requirement:** Documentation of a DSM diagnosis consistent with the presenting problem(s), history, mental status examination and other assessment data.

The diagnosis must be clinically justified — it must follow logically from what the assessment sections document. The rule first confirms that a DSM/ICD code format (`F` or `Z` code) is present somewhere in the note. The AI judge then evaluates whether the diagnosis is supported by the presenting problem, MSE, and assessment data — not whether the diagnosis is correct clinically, but whether the record supports it.

**Fail rule (rule path):** No diagnosis section and no DSM/ICD code format found in the note.

**Pass/fail/review (judge path):** When a code is found, the AI judge evaluates clinical alignment. Returns `manual_review` under NullJudge or `--no-ai`.

---

### D9 — Functional impairment documentation

**Applies to:** intake notes (required)

**Payer requirement:** Medical conditions, psychosocial and environmental factors and functional impairment(s) that support understanding of mental health condition.

Functional impairment documentation connects the diagnosis to its real-world impact on the member's daily life, which justifies the level of care and treatment intensity. The rule looks for a "Functional Impairment" or "Impact on Functioning" section, or for keywords like "functional impairment", "GAF", or "WHODAS" in the note body. When keywords are found but no dedicated section exists, the AI judge evaluates the content.

**Pass rule (rule path):** A functional impairment section is present.

**Pass/fail/review (judge path):** When only keywords are found, the AI judge evaluates substance.

**Fail rule:** No section and no relevant keywords found.

---

## E — Treatment plan elements

### E1 — Symptoms/problems tied to diagnosis

**Applies to:** treatment plan notes (required)

**Payer requirement:** Specific symptoms and problems related to the identified diagnosis of the treatment episode.

The treatment plan must start from the diagnosis and enumerate the specific symptoms or problems that are being targeted — not just restate the diagnosis name. The rule looks for a "Problems", "Target Symptoms", or "Problem List" section and checks that it is non-empty.

**Pass rule:** The section is present and has content.

**Fail rule:** No problems section found.

---

### E2 — Problem prioritization

**Applies to:** treatment plan notes (required)

**Payer requirement:** Critical problems that will be the focus of this episode of care are prioritized; any additional problems that are deferred should be noted as such.

The plan must make clear which problems are the primary focus and which are being deferred, so that reviewers and supervisors can verify that clinical attention is appropriately directed. The rule checks for numbered or ordered problems in the section. When no numbering is present, the AI judge evaluates whether prioritization is implied in the narrative.

**Pass rule (rule path):** Problems appear numbered (e.g., "1.", "2)") in the section.

**Pass/fail/review (judge path):** When numbering is absent, the AI judge evaluates whether prioritization is present.

---

### E3 — Level of care rationale

**Applies to:** treatment plan notes (required)

**Payer requirement:** Relates the recommended level of care to the level of impairment.

Payers require that the level of care (outpatient, IOP, inpatient, etc.) be explicitly connected to the member's level of impairment — this justification is what authorizes the service. The rule checks for a level-of-care keyword (outpatient, IOP, PHP, inpatient, residential, etc.) and also for impairment-related language ("impairment", "functioning", "severity", "symptoms"). The AI judge then evaluates whether the connection between LOC and impairment is explicit.

**Fail rule (rule path):** No level-of-care keyword found; or a LOC is named but no impairment language is near it.

**Pass/fail/review (judge path):** When both are present, the AI judge evaluates whether the rationale explicitly links them.

---

### E4 — Member involvement in planning

**Applies to:** treatment plan notes (required)

**Payer requirement:** Member (and, when indicated, family) involvement in treatment planning.

Collaborative treatment planning is both an ethical standard and a payer requirement. The member (and family when appropriate) must be documented as having participated in, agreed to, or signed the treatment plan. The rule looks for phrases like "member participated", "member agreed", "patient signed", or "consumer involvement". When these phrases are absent, the AI judge evaluates the full note.

**Pass rule (rule path):** Participation language is found.

**Pass/fail/review (judge path):** When keywords are absent, the AI judge evaluates whether participation is documented in the narrative.

---

### E5 — SMART goals

**Applies to:** treatment plan notes (required)

**Payer requirement:** Treatment goals must be specific, behavioral, measurable and realistic.

Goals that are vague ("improve mood") cannot be evaluated for progress and do not meet the payer standard. The rule first applies a heuristic check for measurable language — percentage reductions, frequency words, numeric scales, phrases like "reduce from X to Y". Regardless of whether the heuristic fires, the AI judge evaluates each goal on all four SMART dimensions.

**Pass/fail/review:** Determined by the AI judge (always invoked for this check). Returns `manual_review` under NullJudge or `--no-ai`.

**Fail rule (rule path only):** No goals section found.

---

### E6 — Goal time frames

**Applies to:** treatment plan notes (required)

**Payer requirement:** Treatment goals must include a time frame for goal attainment.

Every goal must specify when it is expected to be achieved — a deadline or duration makes the goal measurable and creates accountability. The rule searches the goals section for time-frame language, including: explicit dates (`by 4/14/2026`), parenthesised dates (`(4/14/2026)`), the phrase "Estimated Completion", duration phrases (`within 6 months`, `in 3 weeks`, `over the next 6 months`), and spelled-out durations (`over the next six months`, `over the next several months`).

**Pass rule:** Any time-frame pattern is found in the goals section.

**Fail rule:** The goals section is present but contains no time-frame language, or no goals section is found at all.

---

### E7 — Progress toward goals

**Applies to:** treatment plan notes (required — especially treatment plan updates/revisions)

**Payer requirement:** Progress or lack of progress towards treatment goals.

Updated treatment plans must document how the member is doing on each goal — not just list the goals again. The rule looks for progress annotation words in the goals section: "progressing", "improved", "met goal", "not met", "no progress", "stagnant", "achieved", "partially met", etc. When these are absent, the AI judge evaluates the content.

**Pass rule (rule path):** Progress annotation language is found.

**Pass/fail/review (judge path):** When keywords are absent, the AI judge evaluates whether progress is documented in the narrative.

---

### E8 — Rationale for treatment length

**Applies to:** treatment plan notes (required)

**Payer requirement:** Rationale for the estimated length of the treatment episode.

The plan must not only state how long treatment is estimated to last, but explain why — connecting the estimated duration to the member's clinical complexity and goals. The rule searches for a "Length of Treatment" or "Estimated Duration" section or an inline phrase with those words. The AI judge then evaluates whether the content provides a rationale rather than just a number.

**Fail rule (rule path):** No treatment-length text found anywhere in the note.

**Pass/fail/review (judge path):** When length text is found, the AI judge evaluates whether rationale (not just a number) is present.

---

### E9 — Goal updates on revision

**Applies to:** treatment plan notes (required — specifically for plan revisions)

**Payer requirement:** Updates to the treatment plan whenever goals are achieved or new problems are identified.

When a treatment plan is revised, it must document what changed: goals that were achieved, goals that were modified, or new problems that were added. The rule looks for revision language like "plan updated", "goal achieved", "goal modified", "new problem", "added". When this language is absent, the AI judge evaluates the full note.

**Pass rule (rule path):** Revision language is found.

**Pass/fail/review (judge path):** When keywords are absent, the AI judge evaluates whether updates are documented.

---

### E10 — Re-evaluation when progress stalls

**Applies to:** treatment plan notes (conditional — only active when lack of progress is documented)

**Payer requirement:** If the member is not progressing towards specified goals, the treatment plan should be re-evaluated to address the lack of progress and modify goals and interventions as needed.

When a note acknowledges stalled progress, the plan must respond — modifying goals or changing interventions. The rule first checks whether stagnation language is present ("no progress", "not progressing", "stagnant", "lack of progress"). If it is, the rule then looks for modification language ("modified", "revised", "new goal", "new intervention"). When modification language is absent despite stagnation, the AI judge evaluates the response.

**Not-applicable:** No stagnation language found — this check only activates when the plan acknowledges lack of progress.

**Pass rule (rule path):** Stagnation is noted AND modification language is present.

**Pass/fail/review (judge path):** Stagnation is noted but modification language is absent — the AI judge evaluates whether the plan responds adequately.

---

## F — Progress note elements

### F1 — Clinician signature

**Applies to:** progress, group, family, and discharge notes (required)

**Payer requirement:** Signature of the practitioner rendering services.

A signed note confirms that a licensed clinician reviewed and attested to the content. The rule looks for the EHR's standard signature block on the last page of the note, which follows the pattern: `Name, Credential, Degree Title, License ST XXXXXX, signed this note`. A fallback search for "signed this note" or "electronically signed" also satisfies the rule.

**Pass rule:** A signature block or signature statement is found on the last page.

**Fail rule:** No signature found on the last page.

---

### F2 — Date of service

**Applies to:** all document types (required)

**Payer requirement:** The date of service.

The date of service is the most fundamental metadata in a clinical record — it anchors every other piece of information in time. The rule reads the date directly from the `Date and Time:` header field that the EHR places on every note's first page.

**Pass rule:** The date of service is extractable from the header.

**Fail rule:** The date of service field is absent or unreadable.

---

### F3 — Telehealth documentation

**Applies to:** all document types (conditional — only active when the session appears to have been delivered via telehealth)

**Payer requirement:** If provided through telehealth, documentation of the use of this technology.

When a session is delivered remotely, the record must say so. The rule detects telehealth in two ways: the `Location:` field contains "telehealth", "virtual", "remote", "phone", or "video"; or the service code contains a telehealth modifier (95, GT, GQ, POS 02, POS 10, modifier 93). When telehealth is detected, the rule checks the note body for keywords like "telehealth", "teletherapy", "video", "audio-only", or "phone".

**Not-applicable:** No indication the session was delivered via telehealth.

**Pass rule:** Telehealth is detected by location/code AND telehealth language appears in the note body. Also passes if telehealth keywords appear in the body without a location/code trigger (the note itself documents it).

**Fail rule:** Location or service code indicates telehealth but the note body does not document it.

---

### F4 — Member strengths and limitations

**Applies to:** progress, group, and family notes (required)

**Payer requirement:** Member strengths and limitations in achieving treatment plan goals and objectives.

Progress notes must document what the member brings to treatment (strengths) and what is working against their progress (limitations or barriers), because this drives intervention planning. The rule looks for dedicated "Strengths" and "Limitations/Barriers" sections. If both sections are present, it passes. If they are absent as sections, the rule looks for the two words appearing near each other in the body text before deferring to the AI judge.

**Pass rule (rule path):** Both sections are present; or strength and limitation/barrier keywords appear together in the body.

**Pass/fail/review (judge path):** When sections are absent, the AI judge evaluates whether the note addresses both.

---

### F5 — Interventions consistent with goals

**Applies to:** progress, group, and family notes (required)

**Payer requirement:** Treatment interventions that are consistent with those goals and objectives noted in the treatment plan.

Progress notes must document what the clinician actually did in the session, and those interventions must align with the goals in the member's treatment plan. The rule first checks that interventions are documented (looking for an "Interventions" section or keywords like "CBT", "DBT", "EMDR", "therapeutic", "technique"). When a treatment plan note for the same member is available in the session bundle, the AI judge compares the progress note's interventions to the plan's goals.

**Manual review:** Interventions are documented but no treatment plan is available in the note bundle for cross-reference.

**Pass/fail/review (judge path with bundle):** The AI judge compares interventions to goals.

**Fail rule:** No interventions documented at all.

---

### F6 — Follow-up dates

**Applies to:** progress, group, and family notes (required)

**Payer requirement:** Dates of follow up visits.

The next appointment date must be documented in every progress note to show that care is continuing. The rule looks for a "Next Appointment", "Follow-up", or "Follow Up" section, or a date pattern following words like "next", "follow-up", or "scheduled" in the note body.

**Pass rule:** A follow-up section or a follow-up date reference is found.

**Fail rule:** No follow-up date documented.

---

### F7 — Missed appointment outreach

**Applies to:** progress, group, and family notes (conditional — only active when the note documents a missed or cancelled appointment)

**Payer requirement:** Documentation of missed appointments, including efforts made to outreach the member.

When a member does not attend a scheduled session, the clinician must document the attempt to contact them — a phone call, text, voicemail, or other outreach. The rule first detects missed-appointment language ("no-show", "missed appointment", "cancelled", "did not attend", "DNA"). When found, it then checks for outreach language ("called", "texted", "voicemail", "left message", "outreach", "contact attempt").

**Not-applicable:** No missed/cancelled appointment language in the note.

**Pass rule:** Missed appointment language found AND outreach language found.

**Fail rule:** Missed appointment found but no outreach documented.

---

### F8 — Time-based duration

**Applies to:** progress notes (required); intake and consultation notes (conditional — only for time-based CPT codes); group and family notes (required)

**Payer requirement:** For time-based services only, either start and stop time or total time in session.

Time-based CPT codes (90832, 90834, 90837, and others) are billed based on the duration of the session. The record must document either the total minutes or the start and stop times to support the billing. The rule checks the extracted header for `Duration: N minutes` or for both `start_time` and `end_time` values.

**Pass rule:** Duration in minutes is present, or both start and end times are present.

**Fail rule:** The note is for a time-based service but neither duration nor start/stop times are documented.

---

## G — Discharge planning

### G1 — Ongoing discharge planning

**Applies to:** intake notes (required); treatment plan notes (required); progress notes (conditional — only when discharge planning language is present)

**Payer requirement:** Documentation of on-going discharge planning beginning at the initiation of treatment, including: criteria for discharge; identification of barriers to completion of treatment and interventions to address them; identification of support systems or lack of support systems.

Discharge planning is not something that happens at the end of treatment — the payer requires it to start at intake and be maintained throughout. Three sub-items must be present: discharge criteria (what will indicate the member is ready to end treatment), barriers and interventions (what might prevent completion and how those barriers will be addressed), and support systems (who and what will support the member after discharge, or a note that such systems are lacking).

**Pass rule (rule path):** All three sections — discharge plan/criteria, support systems, and barriers — are present and non-empty.

**Fail rule (rule path):** None of the three sections is found.

**Pass/fail/review (partial match + judge path):** When some but not all sections are found, the AI judge evaluates whether the full note addresses all three sub-items in the narrative.

**Not-applicable (progress):** Progress note with no reference to discharge planning.

---

## H — Discharge summary

### H1 — Reason for treatment episode

**Applies to:** discharge notes (required)

**Payer requirement:** A discharge summary is completed at the end of the treatment episode that includes the reason for treatment episode.

The discharge summary must document why the member entered treatment in the first place — this provides the narrative context for the entire episode. The rule looks for a "Reason for Treatment", "Episode Summary", "Reason for Admission", or "Reason for Episode" section.

**Pass rule:** The section is present and non-empty.

**Fail rule:** No such section found.

---

### H2 — Goals achieved or not achieved

**Applies to:** discharge notes (required)

**Payer requirement:** Summary of the treatment goals that were achieved or reasons the goals were not achieved.

The discharge summary must account for every treatment goal — confirming which were met and explaining why others were not. The rule looks for a "Goals Achieved", "Goal Summary", "Treatment Outcome", or "Outcomes" section. The AI judge then evaluates whether every goal from the treatment plan is addressed.

**Fail rule (rule path):** No goals-outcome section found.

**Pass/fail/review (judge path):** When the section is present, the AI judge evaluates per-goal coverage.

---

### H3 — Specific aftercare plan

**Applies to:** discharge notes (required)

**Payer requirement:** Specific follow up activities/aftercare plan.

The aftercare plan must be specific — named referrals, scheduled appointments, concrete self-care steps — not generic language like "follow up as needed" or "return if symptoms worsen". The rule looks for an "Aftercare Plan" or "Aftercare" section. If generic language is detected in the section, the AI judge evaluates whether enough specificity is present alongside it.

**Fail rule (rule path):** No aftercare section found.

**Pass rule (rule path):** Aftercare section found and contains no generic "follow up as needed" language.

**Pass/fail/review (judge path):** When generic language is detected, the AI judge evaluates whether specific content is also present.

---

## I — Coordination of care

### I1 — Coordination of care documented

**Applies to:** intake, consultation, and discharge notes (required); progress notes (conditional — only when coordination occurred)

**Payer requirement:** Documentation of coordination of care activities between the treating clinician or facility and other behavioral health or medical clinicians, facilities or consultants. If the member refuses, this refusal and the reason must be documented.

Care coordination across providers is essential for member safety and continuity of care. The rule looks for a "Coordination of Care" or "Care Coordination" section, or for keywords like "release of information", "ROI", "collateral contact", or "contacted [provider type]". If the member refused coordination, the note must document the refusal AND the reason; refusal without reason is a fail.

**Pass rule:** Coordination language or a coordination section is found; or refusal plus reason are both documented.

**Fail rule:** No coordination documentation; or refusal is noted but no reason is given.

**Not-applicable (progress):** Progress note with no indication that external coordination occurred.

---

### I2 — Coordination at key milestones

**Applies to:** intake, consultation, and discharge notes (required)

**Payer requirement:** Coordination of care should occur at the time of intake; during treatment; at the time of discharge or termination of care; at the point of transition between levels of care; and at any other point in treatment that may be appropriate.

This standard goes beyond documenting that coordination happened — it requires it to happen at the right moment. For intake notes, coordination should be documented at the time of intake. For discharge notes, at the time of discharge. For consultation notes, at the point of a level-of-care transition. The rule checks for coordination language in the note and then the AI judge evaluates whether it is associated with the appropriate milestone.

**Pass rule (rule path):** Coordination language is found.

**Pass/fail/review (judge path):** When the rule passes, the AI judge evaluates whether the coordination is tied to the milestone appropriate for this note type.

---

## J — Referrals

### J1 — Referrals to services and resources

**Applies to:** intake, progress, consultation, discharge, group, and family notes (conditional — only when an unmet need is identified)

**Payer requirement:** Documentation of referrals to other clinicians, services, community resources, and/or wellness and prevention programs.

When the note identifies a need that the current treating clinician cannot address — a specialty referral, a community resource, a wellness program — that referral must be documented. The rule first detects whether an unmet need is implied ("needs additional", "gap in care", "outside scope", "unable to provide"). When a need is found, it then checks for referral language ("referred to", "referral", "recommended services", "connected to", "community resource"). When a need exists but no referral is found, the AI judge evaluates the full note.

**Not-applicable:** No unmet need and no referral language — coordination check is not triggered.

**Pass rule:** Referral language or a referrals section is found.

**Pass/fail/review (judge path):** An unmet need is identified but no referral language is found; the AI judge evaluates whether a referral is implied or documented elsewhere.

---

## K — Telehealth

### K1 — Telehealth noted in record

**Applies to:** all document types (conditional — same trigger as F3)

**Payer requirement:** If the service is being provided virtually, this must be noted in the treatment record.

K1 is identical to F3 — it surfaces the same check independently in the telehealth section of the report so that telehealth compliance can be reviewed as a group across all document types. The rule and verdict logic are exactly the same: detect telehealth via location field or service code modifier, then verify telehealth language appears in the note body.

**Pass/fail/not-applicable:** Same logic as F3. See [F3 — Telehealth documentation](#f3--telehealth-documentation).

---

### K2 — State-specific telehealth requirements

**Applies to:** all document types (when telehealth is involved)

**Payer requirement:** Many states have specific documentation requirements for telehealth services. Please review the telehealth regulations in the states in which you are licensed to practice.

State telehealth regulations vary significantly — consent requirements, audio-only restrictions, modality disclosures, and cross-state licensing rules differ by state and change frequently. The engine cannot evaluate compliance with state-specific rules from PDF content alone; it does not know which state's law applies or what that law currently requires.

**Verdict:** Always `manual_review`. The rationale directs the reviewer to check the telehealth regulations for the state(s) in which the clinician is licensed. This is intentional — the standard is explicitly flagged rather than silently omitted, so the audit is complete even where automated evaluation is impossible.
