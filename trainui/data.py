"""
Static data tables for the standards-evaluation UI.

ALL_CHECKS       — one instance per compliance check (49 total)
STANDARD_TITLES  — human-readable title per standard ID
STANDARD_ORDER   — canonical ordering of all standard IDs
REWRITABLE_STANDARDS — standards eligible for mechanical PDF rewrite
STANDARD_TEXT    — verbatim payer language per standard ID
SECTIONS_FOR_STANDARD — canonical section keys each check queries
"""

from __future__ import annotations

from compliance.checks import (
    a_identification, b_entry, c_medication, d_assessment,
    e_treatment_plan, f_progress, g_discharge_planning,
    h_discharge_summary, i_coordination, j_referrals, k_telehealth,
)

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

STANDARD_ORDER: list[str] = list(STANDARD_TITLES.keys())

# Standards that can be fixed via a mechanical PDF rewrite (administrative
# metadata and boilerplate only). Standards NOT in this set must NOT show a
# rewrite affordance — remediation requires clinical documentation, not editing.
# This boundary is a medico-legal constraint, not an implementation gap.
REWRITABLE_STANDARDS: set[str] = {
    "A1",   # Member identification fields (admin metadata)
    "A2",   # Emergency contact (admin metadata)
    "A3",   # Employer / school (admin metadata)
    "B1",   # Date/time of service (admin metadata in header)
    "B2",   # Late entry note (admin metadata — timestamp)
    "F6",   # Clinician name and credential (the primary title-fix standard)
    "F7",   # Clinician signature/license (signature block fix)
    "K1",   # Telehealth delivery statement (boilerplate phrase)
}

# Verbatim payer language from Record Standards.txt, mapped to each standard ID.
STANDARD_TEXT: dict[str, str] = {
    "A1": (
        "The member's name or identification number on each page of the record."
    ),
    "A2": (
        "The member's address; employer or school; home and work telephone numbers, "
        "including emergency contacts; marital or legal status; appropriate consent "
        "forms; and guardianship information."
    ),
    "A3": (
        "The date of service, either start and stop time or total time in session "
        "(for time-based services), notation of session attendees, diagnosis, services "
        "rendered, the rendering clinician's name, professional degree, license and "
        "relevant identification number as applicable."
    ),
    "A4": (
        "For group sessions, the subject covered in the session on the date of service "
        "must be indicated."
    ),
    "A5": (
        "For family sessions, list everyone who attended the session and relationship "
        "to each other."
    ),
    "B1": (
        "Treatment record entries should be made on the date services are rendered and "
        "include the date of service. If an entry is made more than 24 hours after the "
        "service was rendered, the entry should include the date of service, date of "
        "the entry and a notation that it is a late entry."
    ),
    "B2": (
        "Clear and uniform modifications. Any error is to be lined through so that it "
        "can still be read, then dated and initialed by the person making the change."
    ),
    "C1": (
        "Clear documentation of medication allergies, adverse reactions and relevant "
        "medical conditions. If the member has no relevant medical history, this should "
        "be prominently noted."
    ),
    "C2a": (
        "Standing, as needed (PRN) and immediate (STAT) orders for all prescription "
        "and over-the-counter medications."
    ),
    "C2b": (
        "The date medications are prescribed along with the dosage and frequency."
    ),
    "C2c": (
        "Informed member consent for medication, including the member's understanding "
        "of the potential benefits, risks, side effects and alternatives to the "
        "medications."
    ),
    "C2d": (
        "Changes or rationale for lack of changes in medication and/or dosage should "
        "be clearly documented along with the clinical rationale for the changes."
    ),
    "C2e": (
        "Discharge summaries should specify all medications/dosages at the time of "
        "discharge."
    ),
    "D1": (
        "A clear summary of presenting problems, the results of mental status exam(s), "
        "relevant psychological and social conditions affecting the member's medical "
        "and psychiatric status, and the source of such information."
    ),
    "D2": (
        "Prominent documentation (assessment and reassessment) of special status "
        "situations, when present, including, but not limited to, imminent risk of "
        "harm, suicidal or homicidal ideation, self-injurious behaviors, or elopement "
        "potential (for all overnight levels of care). It is also important to document "
        "the absence of such conditions."
    ),
    "D3": (
        "A medical and psychiatric history including previous treatment dates, clinician "
        "or facility identification, therapeutic interventions and responses, sources of "
        "clinical data and relevant family information."
    ),
    "D4": (
        "The behavioral health history includes an assessment of any history of abuse "
        "the member has experienced."
    ),
    "D5": (
        "For adolescents, the assessment documents a sexual behavior history."
    ),
    "D6": (
        "For children and adolescents, past medical and psychiatric history should "
        "include prenatal and perinatal events, along with a complete developmental "
        "history (physical, psychological, social, intellectual and academic)."
    ),
    "D7": (
        "For members 12 years of age and older, documentation includes past and present "
        "use of nicotine or alcohol, as well as illicit drugs, prescribed or "
        "over-the-counter medications."
    ),
    "D8": (
        "Documentation of a DSM diagnosis consistent with the presenting problem(s), "
        "history, mental status examination and other assessment data."
    ),
    "D9": (
        "Medical conditions, psychosocial and environmental factors and functional "
        "impairment(s) that support understanding of mental health condition. This can "
        "include elements of a physical examination, writing a prescription or modifying "
        "psychiatric treatment."
    ),
    "E1": (
        "Specific symptoms and problems related to the identified diagnosis of the "
        "treatment episode."
    ),
    "E2": (
        "Critical problems that will be the focus of this episode of care are "
        "prioritized; any additional problems that are deferred should be noted as such."
    ),
    "E3": (
        "Relates the recommended level of care to the level of impairment."
    ),
    "E4": (
        "Member (and, when indicated, family) involvement in treatment planning."
    ),
    "E5": (
        "Treatment goals must be specific, behavioral, measurable and realistic."
    ),
    "E6": (
        "Treatment goals must include a time frame for goal attainment."
    ),
    "E7": (
        "Progress or lack of progress towards treatment goals."
    ),
    "E8": (
        "Rationale for the estimated length of the treatment episode."
    ),
    "E9": (
        "Updates to the treatment plan whenever goals are achieved or new problems "
        "are identified."
    ),
    "E10": (
        "If the member is not progressing towards specified goals, the treatment plan "
        "should be re-evaluated to address the lack of progress and modify goals and "
        "interventions as needed."
    ),
    "F1": (
        "Progress notes include the signature of the practitioner rendering services."
    ),
    "F2": (
        "Progress notes include the date of service."
    ),
    "F3": (
        "If provided through telehealth, documentation of the use of this technology."
    ),
    "F4": (
        "Member strengths and limitations in achieving treatment plan goals and "
        "objectives."
    ),
    "F5": (
        "Treatment interventions that are consistent with those goals and objectives "
        "noted in the treatment plan."
    ),
    "F6": (
        "Dates of follow up visits."
    ),
    "F7": (
        "Documentation of missed appointments, including efforts made to outreach "
        "the member."
    ),
    "F8": (
        "For time-based services only, either start and stop time or total time in "
        "session."
    ),
    "G1": (
        "Documentation of on-going discharge planning (beginning at the initiation of "
        "treatment) includes the following elements: criteria for discharge; "
        "identification of barriers to completion of treatment and interventions to "
        "address them; identification of support systems or lack of support systems."
    ),
    "H1": (
        "A discharge summary is completed at the end of the treatment episode that "
        "includes the reason for treatment episode."
    ),
    "H2": (
        "Summary of the treatment goals that were achieved or reasons the goals were "
        "not achieved."
    ),
    "H3": (
        "Specific follow up activities/aftercare plan."
    ),
    "I1": (
        "Documentation of coordination of care activities between the treating clinician "
        "or facility and other behavioral health or medical clinicians, facilities or "
        "consultants. If the member refuses to allow coordination of care to occur, this "
        "refusal and the reason for the refusal must be documented."
    ),
    "I2": (
        "Coordination of care should occur: at the time of intake; during treatment; "
        "at the time of discharge or termination of care; at the point of transition "
        "between levels of care; and at any other point in treatment that may be "
        "appropriate."
    ),
    "J1": (
        "Documentation of referrals to other clinicians, services, community resources, "
        "and/or wellness and prevention programs."
    ),
    "K1": (
        "Telehealth Services: If the service is being provided virtually, this must be "
        "noted in the treatment record."
    ),
    "K2": (
        "Many states have specific documentation requirements for telehealth services. "
        "Please review the telehealth regulations in the states in which you are "
        "licensed to practice."
    ),
}

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
