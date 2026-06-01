"""
Section extractor — find named sections in the body of a clinical note.

Section headers are EHR-specific; this module maintains a synonym table
so each canonical name maps to the set of header strings the EHR may use.
Call `extract_sections(full_text)` to get a dict {canonical_name: body_text}.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# dummylink artifact removal
# The EHR injects a "dummylink" anchor that can overlap with body characters.
# Strip it before any section matching.
# ---------------------------------------------------------------------------

RE_DUMMYLINK = re.compile(
    r"d\s*u\s*m\s*m\s*y\s*l\s*i\s*n\s*k",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Remove dummylink artifacts."""
    return RE_DUMMYLINK.sub("", text)


# ---------------------------------------------------------------------------
# Canonical section name → list of possible header phrases (case-insensitive)
# ---------------------------------------------------------------------------

SECTION_SYNONYMS: dict[str, list[str]] = {
    # Demographics / consents
    "address":              ["address", "mailing address", "home address"],
    "employer":             ["employer", "school", "place of employment"],
    "phone":                ["home phone", "work phone", "phone", "telephone"],
    "emergency_contact":    ["emergency contact"],
    "marital_status":       ["marital status", "legal status", "relationship status"],
    "consent":              ["consent", "informed consent form", "consent for treatment"],
    "guardianship":         ["guardian", "guardianship", "legal guardian"],

    # Medical / medication
    "allergies":            ["allergies", "allergy", "drug allergies", "nkda"],
    "medical_history":      ["medical history", "past medical history", "pmh",
                             "relevant medical conditions"],
    "medications":          ["medications", "current medications", "medication list",
                             "med list", "meds"],
    "medications_at_discharge": ["medications at discharge", "discharge medications",
                                 "meds at discharge"],

    # Assessment
    "presenting_problem":   ["presenting problem", "presenting problems",
                             "reason for visit", "chief complaint", "presenting concern"],
    "mse":                  ["mental status exam", "mental status examination",
                             "mse", "mental status"],
    "psychosocial_history": ["psychosocial history", "social history",
                             "psychosocial and environmental factors"],
    "special_status":       ["risk assessment", "safety assessment", "risk factors",
                             "suicidality", "suicide risk", "si/hi", "special status"],
    "psychiatric_history":  ["past psychiatric history", "psychiatric history",
                             "pph", "mental health history"],
    "abuse_history":        ["abuse history", "trauma history", "history of abuse",
                             "trauma and abuse history", "adverse childhood"],
    "sexual_history":       ["sexual history", "sexual behavior history"],
    "developmental_history":["developmental history", "prenatal history",
                             "perinatal history", "developmental milestones"],
    "substance_use":        ["substance use history", "substance abuse history",
                             "alcohol and drug history", "sud history",
                             "substance use", "drug and alcohol"],
    "diagnosis":            ["diagnosis", "diagnoses", "dsm diagnosis",
                             "diagnostic impression", "icd codes"],
    "functional_impairment":["functional impairment", "impact on functioning",
                             "functional assessment", "gaf", "whodas"],

    # Treatment plan
    "problems":             ["problems", "target symptoms", "problem list",
                             "treatment problems"],
    "goals":                ["goals", "treatment goals", "goal", "objectives"],
    "level_of_care":        ["level of care", "loc", "recommended level of care"],
    "member_involvement":   ["member involvement", "patient involvement",
                             "consumer involvement"],
    "treatment_length":     ["length of treatment", "estimated duration",
                             "treatment duration", "episode length"],

    # Progress note
    "strengths":            ["strengths", "member strengths", "client strengths"],
    "limitations":          ["limitations", "barriers", "challenges"],
    "interventions":        ["interventions", "therapeutic interventions",
                             "treatment interventions"],
    "follow_up":            ["next appointment", "follow-up", "follow up",
                             "next session"],
    "missed_appointment":   ["no show", "missed appointment", "cancelled",
                             "cancellation", "outreach"],

    # Group / family
    "topic":                ["topic", "subject", "session focus", "session topic",
                             "group topic"],
    "participants":         ["participants", "attendees", "session participants"],

    # Discharge planning
    "discharge_plan":       ["discharge plan", "discharge planning",
                             "discharge criteria", "criteria for discharge"],
    "support_systems":      ["support systems", "social support", "natural supports"],
    "barriers":             ["barriers", "barriers to treatment",
                             "barriers to discharge"],

    # Discharge summary
    "reason_for_episode":   ["reason for treatment", "episode summary",
                             "reason for admission", "reason for episode"],
    "goals_achieved":       ["goals achieved", "goal summary", "treatment outcome",
                             "outcomes"],
    "aftercare":            ["aftercare plan", "aftercare", "aftercare planning",
                             "discharge aftercare"],

    # Coordination
    "coordination":         ["coordination of care", "care coordination",
                             "release of information", "roi",
                             "communication with", "collateral contact"],

    # Referrals
    "referrals":            ["referrals", "referred to", "referral",
                             "recommended services", "community resources"],

    # Telehealth
    "telehealth":           ["telehealth", "teletherapy", "video session",
                             "provided via", "delivered via", "audio only",
                             "telephonic"],
}

# ---------------------------------------------------------------------------
# Pattern cache — rebuilt whenever the config file mtime changes.
# Key: mtime string of rules/section_synonyms.yaml ("no_config" if absent).
# ---------------------------------------------------------------------------

_PATTERN_CACHE: dict[str, dict[str, re.Pattern]] = {}


def _get_patterns() -> dict[str, re.Pattern]:
    """
    Return compiled section patterns, merging SECTION_SYNONYMS (code default)
    with any overrides in rules/section_synonyms.yaml (config).  When the
    config file changes the cache is rebuilt; otherwise it is returned as-is.
    """
    from compliance.config import RULES_DIR, get_section_synonyms
    config_path = RULES_DIR / "section_synonyms.yaml"
    try:
        cache_key = str(config_path.stat().st_mtime)
    except FileNotFoundError:
        cache_key = "no_config"

    if cache_key in _PATTERN_CACHE:
        return _PATTERN_CACHE[cache_key]

    # Merge: start with code defaults, then let config override per-key.
    merged: dict[str, list[str]] = {k: list(v) for k, v in SECTION_SYNONYMS.items()}
    for canon, syns in get_section_synonyms().items():
        if isinstance(syns, list):
            merged[canon] = syns   # config fully replaces this canonical key

    patterns: dict[str, re.Pattern] = {}
    for canon, syns in merged.items():
        alts = "|".join(re.escape(s) for s in sorted(syns, key=len, reverse=True))
        patterns[canon] = re.compile(
            rf"(?:^|\n)[ \t]*(?:{alts})[ \t]*:?[ \t]*\n?",
            re.IGNORECASE,
        )

    _PATTERN_CACHE.clear()           # only keep the latest entry
    _PATTERN_CACHE[cache_key] = patterns
    return patterns


def extract_sections(full_text: str) -> dict[str, str]:
    """
    Return {canonical_name: body_text} for every section found in full_text.
    Body text runs until the next recognised section header or end of text.
    """
    cleaned = _clean(full_text)

    # Find all section starts with their canonical names.
    hits: list[tuple[int, str]] = []
    for canon, pattern in _get_patterns().items():
        for m in pattern.finditer(cleaned):
            hits.append((m.end(), canon))

    if not hits:
        return {}

    hits.sort(key=lambda x: x[0])

    sections: dict[str, str] = {}
    for i, (start, canon) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(cleaned)
        body = cleaned[start:end].strip()
        # If the same canonical section appears more than once (e.g. repeated
        # Diagnosis on every page), concatenate.
        if canon in sections:
            sections[canon] = sections[canon] + "\n" + body
        else:
            sections[canon] = body

    return sections


def has_section(sections: dict[str, str], *names: str) -> bool:
    """True if any of the given canonical names has non-empty body text."""
    return any(bool(sections.get(n, "").strip()) for n in names)


def get_section(sections: dict[str, str], *names: str) -> str:
    """Return the first non-empty body found among the given canonical names."""
    for n in names:
        v = sections.get(n, "").strip()
        if v:
            return v
    return ""
