"""
Static data tables for the standards-evaluation UI.

The Ruleset object (compliance.ruleset) is now the single source of truth for
all per-payer data: ALL_CHECKS, STANDARD_TITLES, STANDARD_ORDER, STANDARD_TEXT.

This module re-exports those from the active ruleset for back-compat, and keeps
the two tables that are genuinely shared across all payers:
  REWRITABLE_STANDARDS  — medico-legal boundary (shared, not payer policy)
  SECTIONS_FOR_STANDARD — check-level fact: which sections each check queries

Usage:
  from trainui.data import get_checks_for, get_titles_for, SECTIONS_FOR_STANDARD
  # OR with a specific ruleset:
  from compliance.ruleset import get_ruleset
  rs = get_ruleset("medicaid_co")
  checks = rs.checks()
"""

from __future__ import annotations

from compliance.ruleset import Ruleset, get_ruleset


def get_checks_for(ruleset: Ruleset | None = None):
    """Return Check instances in manifest order for the given ruleset."""
    return (ruleset or get_ruleset()).checks()


def get_standard_order_for(ruleset: Ruleset | None = None) -> list[str]:
    return (ruleset or get_ruleset()).standard_order


def get_titles_for(ruleset: Ruleset | None = None) -> dict[str, str]:
    rs = ruleset or get_ruleset()
    return {sid: rs.title(sid) for sid in rs.standard_order}


def get_payer_text_for(ruleset: Ruleset | None = None) -> dict[str, str]:
    rs = ruleset or get_ruleset()
    return {sid: rs.payer_text(sid) for sid in rs.standard_order}


# ── Back-compat module-level names (use the default ruleset) ─────────────────
# Code that does `from trainui.data import ALL_CHECKS` will get the default
# ruleset's checks.  Prefer the getter functions above for new code.

def __getattr__(name: str):
    _compat = {
        "ALL_CHECKS":      lambda: get_ruleset().checks(),
        "STANDARD_TITLES": lambda: {sid: get_ruleset().title(sid) for sid in get_ruleset().standard_order},
        "STANDARD_ORDER":  lambda: get_ruleset().standard_order,
        "STANDARD_TEXT":   lambda: {sid: get_ruleset().payer_text(sid) for sid in get_ruleset().standard_order},
    }
    if name in _compat:
        return _compat[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Shared across all payers ──────────────────────────────────────────────────

# Standards eligible for mechanical PDF rewrite.
# This is a medico-legal boundary, not payer policy.
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

# Canonical sections each check looks up (shared — tied to check impl, not payer).
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
