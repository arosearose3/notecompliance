"""
compliance/ruleset.py — Multi-ruleset support.

A Ruleset encapsulates one payer's documentation standards: which standard_ids
exist, their titles and payer text, applicability (R/C/None per doc type),
thresholds, judge prompts, and which Check implementation to use per standard.

Usage
-----
    from compliance.ruleset import get_ruleset, list_rulesets

    ruleset = get_ruleset("optum_commercial")   # or None for default
    checks  = ruleset.checks()                  # ordered list[Check]
    appl    = ruleset.applies("A1", "progress") # "R", "C", or None
    title   = ruleset.title("A1")

Design notes
------------
- The default ruleset is ``optum_commercial`` — behaviour-identical to the
  pre-refactor hardcoded tables in compliance/applicability.py and trainui/data.py.
- Rulesets are loaded from ``rules/<ruleset_id>/ruleset.yaml`` (manifest) plus
  sibling data files (applicability, thresholds, payer_text).  If the per-ruleset
  files are absent the hardcoded DEFAULTS for optum_commercial are used so the
  system works before the migration step moves files into place.
- ``extends`` is supported one level deep: load the base manifest first, then
  overlay deltas from the child.  Chains are rejected at load time.
- The ``applies()`` function and ``get_applicable_standards()`` method both use
  the same resolved applicability source, eliminating the pre-existing divergence.
- Empty-dict applicability rows (B2, K2) mean "run for ALL doc types" (the
  intended behaviour — these checks always fire as manual_review), not "omit".
"""

from __future__ import annotations

import importlib
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compliance.checks.base import Check

# ── Repo-root paths ──────────────────────────────────────────────────────────

_RULES_ROOT = Path(__file__).resolve().parent.parent / "rules"
DEFAULT_RULESET_ID = "optum_commercial"

# ── Default (hardcoded) tables for optum_commercial ─────────────────────────
# These are the single source of truth while rules/optum_commercial/ doesn't
# yet exist on disk.  Once the migration step runs, the YAML files take over.

_DEFAULT_STANDARDS: list[dict] = [
    {"id": "A1",  "title": "Member ID on each page"},
    {"id": "A2",  "title": "Demographics, contacts, consent"},
    {"id": "A3",  "title": "Encounter metadata (date, duration, clinician, diagnosis, service code)"},
    {"id": "A4",  "title": "Group session — subject covered"},
    {"id": "A5",  "title": "Family session — attendees and relationships"},
    {"id": "B1",  "title": "Late entry notation"},
    {"id": "B2",  "title": "Modification audit trail"},
    {"id": "C1",  "title": "Allergies and medical conditions"},
    {"id": "C2a", "title": "Medication order types (standing/PRN/STAT)"},
    {"id": "C2b", "title": "Medication date, dose, and frequency"},
    {"id": "C2c", "title": "Medication informed consent"},
    {"id": "C2d", "title": "Medication change/no-change rationale"},
    {"id": "C2e", "title": "Discharge medication list with doses"},
    {"id": "D1",  "title": "Presenting problem, MSE, psychosocial, source"},
    {"id": "D2",  "title": "Special status assessment (SI/HI/SIB/elopement/harm)"},
    {"id": "D3",  "title": "Medical and psychiatric history"},
    {"id": "D4",  "title": "Abuse and trauma history"},
    {"id": "D5",  "title": "Adolescent sexual behavior history (ages 12–17)"},
    {"id": "D6",  "title": "Child/adolescent developmental history"},
    {"id": "D7",  "title": "Substance use history (age 12+)"},
    {"id": "D8",  "title": "DSM diagnosis consistent with assessment"},
    {"id": "D9",  "title": "Functional impairment documentation"},
    {"id": "E1",  "title": "Symptoms/problems tied to diagnosis"},
    {"id": "E2",  "title": "Problem prioritization; deferred items labelled"},
    {"id": "E3",  "title": "Level of care rationale linked to impairment"},
    {"id": "E4",  "title": "Member involvement in treatment planning"},
    {"id": "E5",  "title": "SMART goals (specific, behavioral, measurable, realistic)"},
    {"id": "E6",  "title": "Goal time frames"},
    {"id": "E7",  "title": "Progress toward goals"},
    {"id": "E8",  "title": "Rationale for estimated treatment length"},
    {"id": "E9",  "title": "Goal updates on revision"},
    {"id": "E10", "title": "Re-evaluation when progress stalls"},
    {"id": "F1",  "title": "Clinician signature"},
    {"id": "F2",  "title": "Date of service"},
    {"id": "F3",  "title": "Telehealth documentation"},
    {"id": "F4",  "title": "Member strengths and limitations toward goals"},
    {"id": "F5",  "title": "Interventions consistent with treatment-plan goals"},
    {"id": "F6",  "title": "Follow-up dates"},
    {"id": "F7",  "title": "Missed appointment outreach documented"},
    {"id": "F8",  "title": "Time-based duration (start/stop or total)"},
    {"id": "G1",  "title": "Ongoing discharge planning (criteria, barriers, support)"},
    {"id": "H1",  "title": "Reason for treatment episode"},
    {"id": "H2",  "title": "Goals achieved or reasons not achieved"},
    {"id": "H3",  "title": "Specific aftercare plan"},
    {"id": "I1",  "title": "Coordination of care (or documented refusal)"},
    {"id": "I2",  "title": "Coordination at key milestones"},
    {"id": "J1",  "title": "Referrals to clinicians, services, community resources"},
    {"id": "K1",  "title": "Telehealth noted in record"},
    {"id": "K2",  "title": "State-specific telehealth requirements"},
]

# The applicability MATRIX from compliance/applicability.py.
# Empty dict = run for ALL doc types (B2, K2 always fire as manual_review).
_ALL_DOC_TYPES = frozenset([
    "intake", "progress", "consultation", "treatment_plan",
    "discharge", "group", "family", "other",
])

_DEFAULT_MATRIX: dict[str, dict[str, str | None]] = {
    "A1": {
        "intake": "R", "progress": "R", "consultation": "R",
        "treatment_plan": "R", "discharge": "R", "group": "R", "family": "R",
    },
    "A2":  {"intake": "R"},
    "A3":  {
        "intake": "R", "progress": "R", "consultation": "R", "discharge": "R",
        "group": "R", "family": "R",
    },
    "A4":  {"progress": "C", "group": "R"},
    "A5":  {"progress": "C", "family": "R"},
    "B1":  {
        "intake": "C", "progress": "C", "consultation": "C",
        "treatment_plan": "C", "discharge": "C", "group": "C", "family": "C",
    },
    "B2":  {},  # empty = run for all doc types
    "C1":  {"intake": "R", "progress": "C", "discharge": "R"},
    "C2a": {"intake": "C", "progress": "C", "discharge": "C"},
    "C2b": {"intake": "C", "progress": "C", "discharge": "C"},
    "C2c": {"intake": "C", "progress": "C", "discharge": "C"},
    "C2d": {"intake": "C", "progress": "C", "discharge": "C"},
    "C2e": {"discharge": "R"},
    "D1":  {"intake": "R", "consultation": "C"},
    "D2":  {"intake": "R", "progress": "C", "consultation": "C"},
    "D3":  {"intake": "R"},
    "D4":  {"intake": "R"},
    "D5":  {"intake": "C"},
    "D6":  {"intake": "C"},
    "D7":  {"intake": "C"},
    "D8":  {"intake": "R"},
    "D9":  {"intake": "R"},
    "E1":  {"treatment_plan": "R"},
    "E2":  {"treatment_plan": "R"},
    "E3":  {"treatment_plan": "R"},
    "E4":  {"treatment_plan": "R"},
    "E5":  {"treatment_plan": "R"},
    "E6":  {"treatment_plan": "R"},
    "E7":  {"treatment_plan": "R"},
    "E8":  {"treatment_plan": "R"},
    "E9":  {"treatment_plan": "R"},
    "E10": {"treatment_plan": "R"},
    "F1":  {"progress": "R", "discharge": "R", "group": "R", "family": "R"},
    "F2":  {
        "intake": "R", "progress": "R", "consultation": "R",
        "treatment_plan": "R", "discharge": "R", "group": "R", "family": "R",
    },
    "F3":  {
        "intake": "C", "progress": "C", "consultation": "C",
        "treatment_plan": "C", "discharge": "C", "group": "C", "family": "C",
    },
    "F4":  {"progress": "R", "group": "R", "family": "R"},
    "F5":  {"progress": "R", "group": "R", "family": "R"},
    "F6":  {"progress": "R", "group": "R", "family": "R"},
    "F7":  {"progress": "C", "group": "C", "family": "C"},
    "F8":  {
        "intake": "C", "progress": "R", "consultation": "C",
        "group": "R", "family": "R",
    },
    "G1":  {"intake": "R", "treatment_plan": "R", "progress": "C"},
    "H1":  {"discharge": "R"},
    "H2":  {"discharge": "R"},
    "H3":  {"discharge": "R"},
    "I1":  {"intake": "R", "consultation": "R", "discharge": "R", "progress": "C"},
    "I2":  {"intake": "R", "consultation": "R", "discharge": "R"},
    "J1":  {
        "intake": "C", "progress": "C", "consultation": "C",
        "discharge": "C", "group": "C", "family": "C",
    },
    "K1":  {
        "intake": "C", "progress": "C", "consultation": "C",
        "treatment_plan": "C", "discharge": "C", "group": "C", "family": "C",
    },
    "K2":  {},  # empty = run for all doc types
}

_DEFAULT_PAYER_TEXT: dict[str, str] = {
    "A1": "The member's name or identification number on each page of the record.",
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
    "C2a": "Standing, as needed (PRN) and immediate (STAT) orders for all prescription and over-the-counter medications.",
    "C2b": "The date medications are prescribed along with the dosage and frequency.",
    "C2c": (
        "Informed member consent for medication, including the member's understanding "
        "of the potential benefits, risks, side effects and alternatives to the medications."
    ),
    "C2d": (
        "Changes or rationale for lack of changes in medication and/or dosage should "
        "be clearly documented along with the clinical rationale for the changes."
    ),
    "C2e": "Discharge summaries should specify all medications/dosages at the time of discharge.",
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
    "D4": "The behavioral health history includes an assessment of any history of abuse the member has experienced.",
    "D5": "For adolescents, the assessment documents a sexual behavior history.",
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
    "E1": "Specific symptoms and problems related to the identified diagnosis of the treatment episode.",
    "E2": (
        "Critical problems that will be the focus of this episode of care are "
        "prioritized; any additional problems that are deferred should be noted as such."
    ),
    "E3": "Relates the recommended level of care to the level of impairment.",
    "E4": "Member (and, when indicated, family) involvement in treatment planning.",
    "E5": "Treatment goals must be specific, behavioral, measurable and realistic.",
    "E6": "Treatment goals must include a time frame for goal attainment.",
    "E7": "Progress or lack of progress towards treatment goals.",
    "E8": "Rationale for the estimated length of the treatment episode.",
    "E9": "Updates to the treatment plan whenever goals are achieved or new problems are identified.",
    "E10": (
        "If the member is not progressing towards specified goals, the treatment plan "
        "should be re-evaluated to address the lack of progress and modify goals and "
        "interventions as needed."
    ),
    "F1": "Progress notes include the signature of the practitioner rendering services.",
    "F2": "Progress notes include the date of service.",
    "F3": "If provided through telehealth, documentation of the use of this technology.",
    "F4": "Member strengths and limitations in achieving treatment plan goals and objectives.",
    "F5": (
        "Treatment interventions that are consistent with those goals and objectives "
        "noted in the treatment plan."
    ),
    "F6": "Dates of follow up visits.",
    "F7": "Documentation of missed appointments, including efforts made to outreach the member.",
    "F8": "For time-based services only, either start and stop time or total time in session.",
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
    "H2": "Summary of the treatment goals that were achieved or reasons the goals were not achieved.",
    "H3": "Specific follow up activities/aftercare plan.",
    "I1": (
        "Documentation of coordination of care activities between the treating clinician "
        "or facility and other behavioral health or medical clinicians, facilities or "
        "consultants. If the member refuses to allow coordination of care to occur, this "
        "refusal and the reason for the refusal must be documented."
    ),
    "I2": (
        "Coordination of care should occur: at the time of intake; during treatment; "
        "at the time of discharge or termination of care; at the point of transition "
        "between levels of care; and at any other point in treatment that may be appropriate."
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

# Map standard prefix → check module name (mirrors _MODULE_FOR_PREFIX in trainui/artifacts.py)
_PREFIX_TO_MODULE = {
    "A": "a_identification", "B": "b_entry",      "C": "c_medication",
    "D": "d_assessment",     "E": "e_treatment_plan", "F": "f_progress",
    "G": "g_discharge_planning", "H": "h_discharge_summary",
    "I": "i_coordination",   "J": "j_referrals",  "K": "k_telehealth",
}


def _default_check_for(standard_id: str) -> "Check":
    """Instantiate the shared default check for a standard_id."""
    prefix = standard_id[0] if standard_id else ""
    module_name = _PREFIX_TO_MODULE.get(prefix)
    if not module_name:
        raise ValueError(f"No check module for standard_id {standard_id!r}")
    module = importlib.import_module(f"compliance.checks.{module_name}")
    class_name = f"Check{standard_id}"
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"{module_name}.{class_name} not found")
    return cls()


def _load_yaml(path: Path) -> dict | list:
    """Load a YAML file; return empty dict on missing file."""
    if not path.is_file():
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _load_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()


# ── Ruleset class ────────────────────────────────────────────────────────────

class Ruleset:
    """
    One payer's documentation standard set, fully resolved.

    Constructed by ``_load_ruleset``; consumed by the runner, trainui, and
    report writers.  All state is immutable after construction.
    """

    def __init__(
        self,
        ruleset_id: str,
        label: str,
        description: str,
        standards: list[dict],          # [{id, title, impl?}]
        matrix: dict[str, dict],        # sid -> {doc_type -> R/C/None}
        payer_text_map: dict[str, str], # sid -> verbatim payer text
        thresholds: dict,               # key -> value
        rules_dir: Path,
    ) -> None:
        self.id = ruleset_id
        self.label = label
        self.description = description
        self._standards = standards
        self._matrix = matrix
        self._payer_text = payer_text_map
        self._thresholds = thresholds
        self.rules_dir = rules_dir

        # Build ordered list of standard_ids
        self.standard_order: list[str] = [s["id"] for s in standards]

        # Build title map
        self._titles: dict[str, str] = {s["id"]: s.get("title", s["id"]) for s in standards}

        # Build impl map (standard_id -> dotted.path or None)
        self._impls: dict[str, str | None] = {
            s["id"]: s.get("impl") for s in standards
        }

    def checks(self) -> list["Check"]:
        """Return Check instances in manifest order, resolving impl overrides."""
        result = []
        for sid in self.standard_order:
            impl_path = self._impls.get(sid)
            if impl_path:
                # Code-varies override: import and instantiate
                parts = impl_path.rsplit(".", 1)
                if len(parts) != 2:
                    raise ValueError(f"impl {impl_path!r} must be a dotted class path")
                module = importlib.import_module(parts[0])
                cls = getattr(module, parts[1])
                result.append(cls())
            else:
                result.append(_default_check_for(sid))
        return result

    def title(self, standard_id: str) -> str:
        return self._titles.get(standard_id, standard_id)

    def payer_text(self, standard_id: str) -> str:
        return self._payer_text.get(standard_id, "")

    def applies(self, standard_id: str, doc_type: str) -> str | None:
        """
        Return "R", "C", or None for the given standard and doc type.

        Empty-dict rows (B2, K2) mean "applies to ALL doc types" — these
        checks always run and return manual_review.  This is the intended
        behaviour, not "omit".
        """
        row = self._matrix.get(standard_id)
        if row is None:
            return None                      # standard not in this ruleset
        if not row:                          # empty dict — run for all doc types
            return "C"                       # conditional = "may apply, check at runtime"
        return row.get(doc_type)

    def get_applicable_standards(self, doc_type: str) -> list[str]:
        """
        Return all standard_ids that have any applicability for the given doc type.
        Uses the same resolved source as applies(), so they always agree.
        """
        result = []
        for sid in self.standard_order:
            row = self._matrix.get(sid, {})
            if not row:
                # Empty dict = run for all doc types
                result.append(sid)
            elif doc_type in row:
                result.append(sid)
        return result

    def threshold(self, key: str, default=None):
        return self._thresholds.get(key, default)

    def prompt(self, standard_id: str) -> str | None:
        """Return judge prompt override for a standard, or None."""
        path = self.rules_dir / "prompts" / f"{standard_id}.md"
        return _load_text(path)

    def corpus_path(self) -> Path:
        return self.rules_dir / "corpus.json"

    def __repr__(self) -> str:
        return f"Ruleset({self.id!r}, {len(self.standard_order)} standards)"


# ── Loader ────────────────────────────────────────────────────────────────────

def _load_ruleset(ruleset_id: str, _seen: set[str] | None = None) -> Ruleset:
    """
    Load and fully resolve a Ruleset from rules/<ruleset_id>/ruleset.yaml.

    Falls back to hardcoded defaults for optum_commercial when the file is
    absent (back-compat during the migration step).
    """
    if _seen is None:
        _seen = set()
    if ruleset_id in _seen:
        raise ValueError(
            f"Circular ruleset extends detected: {_seen} -> {ruleset_id}"
        )
    _seen = _seen | {ruleset_id}

    rules_dir = _RULES_ROOT / ruleset_id
    manifest_path = rules_dir / "ruleset.yaml"

    # --- Load manifest ---
    if manifest_path.is_file():
        manifest = _load_yaml(manifest_path)
        if not isinstance(manifest, dict):
            manifest = {}
    else:
        # Back-compat: use hardcoded defaults for optum_commercial
        if ruleset_id == DEFAULT_RULESET_ID:
            manifest = {}
        else:
            raise FileNotFoundError(
                f"Ruleset manifest not found: {manifest_path}"
            )

    label       = manifest.get("label", ruleset_id)
    description = manifest.get("description", "")
    extends_id  = manifest.get("extends")

    # --- Handle inheritance (one level only) ---
    if extends_id:
        if _seen and extends_id in _seen:
            raise ValueError(
                f"Ruleset {ruleset_id!r} extends {extends_id!r} which is "
                f"itself extending something — only one level of extends is allowed."
            )
        base = _load_ruleset(extends_id, _seen)

        # Start from base and overlay deltas
        base_standards_map = {s["id"]: dict(s) for s in
                              (base._standards if hasattr(base, "_standards") else [])}
        overlay_standards = {s["id"]: s for s in manifest.get("standards", [])}
        # Merge: base first, then overlay (child wins)
        merged = dict(base_standards_map)
        for sid, s in overlay_standards.items():
            merged[sid] = {**merged.get(sid, {}), **s}
        # Preserve base order, appending new sids at end
        order = list(base.standard_order)
        for sid in overlay_standards:
            if sid not in order:
                order.append(sid)
        standards = [merged[sid] for sid in order if sid in merged]

        base_matrix = dict(base._matrix)
    else:
        standards = manifest.get("standards", [])
        base_matrix = {}

    # If no standards in manifest, use defaults
    if not standards and ruleset_id == DEFAULT_RULESET_ID:
        standards = _DEFAULT_STANDARDS

    # --- Applicability ---
    appl_path = rules_dir / "applicability.yaml"
    if appl_path.is_file():
        appl_override = _load_yaml(appl_path)
        if not isinstance(appl_override, dict):
            appl_override = {}
    else:
        appl_override = {}

    if extends_id:
        matrix = dict(base_matrix)
        matrix.update(appl_override)
    elif ruleset_id == DEFAULT_RULESET_ID:
        matrix = dict(_DEFAULT_MATRIX)
        matrix.update(appl_override)
    else:
        matrix = appl_override

    # --- Thresholds ---
    # Start from base (or defaults for optum_commercial), then overlay file values.
    if extends_id:
        thresholds = dict(base._thresholds)
    elif ruleset_id == DEFAULT_RULESET_ID:
        thresholds = {"late_entry_hours": 24}
    else:
        thresholds = {}

    thresh_path = rules_dir / "thresholds.yaml"
    if thresh_path.is_file():
        overlay = _load_yaml(thresh_path)
        if isinstance(overlay, dict) and overlay:
            thresholds.update(overlay)

    # --- Payer text ---
    # Start from base, then overlay per-ruleset entries.
    if extends_id:
        payer_text = dict(base._payer_text)
    elif ruleset_id == DEFAULT_RULESET_ID:
        payer_text = dict(_DEFAULT_PAYER_TEXT)
    else:
        payer_text = {}

    pt_path = rules_dir / "payer_text.yaml"
    if pt_path.is_file():
        overlay = _load_yaml(pt_path)
        if isinstance(overlay, dict) and overlay:
            payer_text.update(overlay)

    return Ruleset(
        ruleset_id=ruleset_id,
        label=label,
        description=description,
        standards=standards,
        matrix=matrix,
        payer_text_map=payer_text,
        thresholds=thresholds,
        rules_dir=rules_dir,
    )


# ── Registry ─────────────────────────────────────────────────────────────────

def list_rulesets() -> list[dict]:
    """
    Return [{id, label, description}] for all rulesets discoverable under rules/.
    Always includes optum_commercial even if the directory doesn't exist yet.
    """
    found: dict[str, dict] = {}

    if _RULES_ROOT.is_dir():
        for child in sorted(_RULES_ROOT.iterdir()):
            if child.is_dir() and (child / "ruleset.yaml").is_file():
                manifest = _load_yaml(child / "ruleset.yaml")
                if isinstance(manifest, dict):
                    found[child.name] = {
                        "id":          child.name,
                        "label":       manifest.get("label", child.name),
                        "description": manifest.get("description", ""),
                    }

    # Ensure optum_commercial always appears
    if DEFAULT_RULESET_ID not in found:
        found[DEFAULT_RULESET_ID] = {
            "id":          DEFAULT_RULESET_ID,
            "label":       "Optum / UBH Commercial",
            "description": "Optum Provider Manual Treatment Record Content Standards.",
        }

    return list(found.values())


def get_ruleset(ruleset_id: str | None = None) -> Ruleset:
    """
    Return the named Ruleset, or the default (optum_commercial) if None.
    Results are cached for the process lifetime (use invalidate_ruleset_cache
    to clear after editing manifest files).
    """
    rid = ruleset_id or DEFAULT_RULESET_ID
    return _load_cached(rid)


# Simple cache that can be invalidated
_RULESET_CACHE: dict[str, Ruleset] = {}


def _load_cached(ruleset_id: str) -> Ruleset:
    if ruleset_id not in _RULESET_CACHE:
        _RULESET_CACHE[ruleset_id] = _load_ruleset(ruleset_id)
    return _RULESET_CACHE[ruleset_id]


def invalidate_ruleset_cache(ruleset_id: str | None = None) -> None:
    """Clear the ruleset cache (e.g. after UI edits to manifest files)."""
    if ruleset_id:
        _RULESET_CACHE.pop(ruleset_id, None)
    else:
        _RULESET_CACHE.clear()
