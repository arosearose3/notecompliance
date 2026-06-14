# Plan — Multi-Ruleset Architecture (Commercial, Medicaid, …)

**Status:** design plan. No code in this document. Written to be implemented
directly (target implementer: Sonnet).
**Audience:** the engineer adding support for multiple payer standard sets to the
compliance engine and the training UI.

---

## 1. BLUF

Today the engine encodes exactly **one** payer's rules — Optum/commercial — and
that single standard set is hard-wired into ~6 places (two duplicate
`ALL_CHECKS` lists, `STANDARD_TITLES`, `STANDARD_TEXT`, the applicability
`MATRIX`, and a flat `rules/` directory). The moment a second payer is needed
(Medicaid documentation rules differ from Commercial), there is no seam to add
it without forking the whole engine.

This plan introduces **one new concept — the *ruleset*** — as a first-class
dimension, and threads it through evaluation, the training UI, reports, and
rewrite. The design is deliberately small:

> **A ruleset is a manifest** (which `standard_id`s exist, their order, titles,
> payer text, applicability, thresholds, and prompts) **plus a map
> `standard_id → check implementation`** that *defaults to the shared check* and
> only names a per-ruleset override when the detection logic genuinely differs.

A new payer is therefore **additive**: a manifest + a few config deltas + the
small handful of checks whose *logic* (not just data) actually differs. The
existing 49 checks are not rewritten.

**The #1 invariant (the regression gate for every step):** the current 49 checks
+ MATRIX + titles/text become one named ruleset, `optum_commercial`, selected by
default, producing the **identical verdict for every standard on `sourcedocs/`**
before and after this refactor. "Identical" means the **verdict tuple**
(`standard_id`, `verdict`, `rationale`, `page_numbers`) is unchanged — *not*
byte-identical report files, because §5.6 deliberately adds a ruleset-id field
to reports. File-level byte-identity holds only through step 2 (§8); from the
moment the ruleset-id field lands, the gate is verdict-tuple equality modulo that
one added field. Nothing about today's *behavior* changes until a *second*
ruleset is authored.

**Scope guard:** "modular and modern" here means *one source of truth + a
registry indirection + a per-ruleset rules subtree* — **not** a plugin-discovery
/ entry-points framework. That is the over-engineering trap for this request and
is explicitly out of scope (§9).

---

## 2. The core taxonomy: data-varies vs code-varies

Every difference between two payers' rules falls into exactly one of two
buckets, and they get different mechanisms. Classifying each difference is the
whole design.

| Bucket | What differs | Mechanism | Frequency |
|---|---|---|---|
| **Data-varies** | which standards are in the set; applicability (R/C/None) per doc type; numeric thresholds; verbatim payer text; the judge prompt/question | **Same check class**, different per-ruleset *config*. No Python. | Common case |
| **Code-varies** | the detection *logic* genuinely differs (e.g. Medicaid's goal-time-frame rule accepts forms Commercial rejects) | A **per-ruleset check class** that overrides the default in the manifest. Authored via the existing Tier-3 codegen handoff. | Rare |

The decision rule the implementer applies to every payer difference:

> If the difference can be expressed as *set membership, applicability, a
> threshold, payer text, or a prompt* → it is **data**, put it in the ruleset's
> config. Only if the difference is in *how the note is inspected* → it is
> **code**, write a per-ruleset check class and name it in the manifest.

This is why the 49 checks don't get rewritten: the overwhelming majority of
payer variation is data, and data lives in the manifest/config, not in the
check.

---

## 3. The ruleset manifest

A ruleset is declared by a manifest file (YAML) plus a rules subtree. Proposed
location: `rules/<ruleset_id>/ruleset.yaml`.

```yaml
# rules/optum_commercial/ruleset.yaml
id: optum_commercial
label: "Optum / UBH Commercial"
description: "Optum Provider Manual Treatment Record Content Standards."

# Optional single-level inheritance (see §7). Omit for a standalone manifest.
# extends: optum_commercial

# The standards in this set, in display order. Each entry's data lives here;
# the check implementation defaults to the shared class unless `impl` overrides.
# (optum_commercial has NO impl overrides — every standard uses the shared check,
# which is exactly today's behavior. See §8 for a code-varies example in Medicaid.)
standards:
  - id: A1
    title: "Member ID on each page"
    # impl:   (omitted → use the shared default check for A1)
  - id: B1
    title: "Late entry notation"
  - id: E6
    title: "Goal time frames"
  # … all standards for this ruleset …
```

The manifest is the **single source of truth** that today's six hardcoded
tables derive from. Per-ruleset *data* that is verbose (payer text,
applicability, thresholds, prompts) stays in dedicated files under the ruleset's
subtree (§4), referenced by the manifest implicitly via `id`. Keep `ruleset.yaml`
to the standard list + ordering + titles + impl overrides; push bulky tables to
sibling files so the manifest stays readable.

### 3.1 The check-resolution map

For each `standard_id` in the manifest:
- **no `impl`** → resolve to the shared default check
  (`compliance/checks/<module>.Check<ID>`), exactly what runs today.
- **`impl: <dotted.path>`** → import and instantiate that class instead.

**Where code-varies override classes live (their Python home).** Override check
classes are real importable Python, so they live under the `compliance` package,
**not** under `rules/` (which is YAML data, not a package). The convention:
```
compliance/checks/rulesets/<ruleset_id>/<module>.py   # e.g. CheckE6Medicaid
```
with `compliance/checks/rulesets/__init__.py` and a per-ruleset `__init__.py` so
they import cleanly. A manifest's `impl` is the dotted path to such a class, e.g.
`compliance.checks.rulesets.medicaid_co.e_treatment_plan.CheckE6Medicaid`. The
existing **Tier-3 codegen handoff** is the authoring mechanism: it writes the new
override class into this location and adds the `impl` line to the ruleset
manifest. An override class satisfies the same `Check` protocol
(`compliance/checks/base.py`) as any shared check — it is a drop-in, not a
special case.

A `Ruleset` object exposes:
```
Ruleset.id, .label, .standard_order: list[str]
Ruleset.checks() -> list[Check]          # resolved, in manifest order
Ruleset.title(sid) -> str
Ruleset.payer_text(sid) -> str
Ruleset.applies(sid, doc_type) -> "R"|"C"|None
Ruleset.threshold(key, default)
Ruleset.prompt(sid) -> str | None
Ruleset.rules_dir -> Path                # rules/<id>/
```
Everything downstream consumes a `Ruleset`, never the module-level globals.

---

## 4. What is per-ruleset vs shared (classify every `rules/` artifact)

Getting this split right avoids both over-copying (duplicating EHR vocabulary
per payer) and under-copying (sharing a corpus that's only meaningful within one
ruleset).

| Artifact | Scope | Why |
|---|---|---|
| `applicability.yaml` (R/C/None) | **per-ruleset** | the heart of what payers differ on |
| `thresholds.yaml` | **per-ruleset** | e.g. late-entry window may differ |
| `prompts/<id>.md` | **per-ruleset** | judge question is payer-specific |
| payer text (now `STANDARD_TEXT`) | **per-ruleset** | verbatim from each payer's manual |
| `rewrites.yaml` (Tier-R1) | **per-ruleset** | remediation phrasing can be payer-specific |
| `corpus.json` (pinned verdicts) | **per-ruleset** | a pinned verdict is only valid *within one ruleset* |
| `section_synonyms.yaml` | **shared** | EHR vocabulary, not payer policy — one EHR emits the same headings regardless of payer |
| doc-type classification (`classify.py`) | **shared** | doc types (intake/progress/…) are universal; standards *over* them vary. **Do not fork `classify.py`.** |
| `SECTIONS_FOR_STANDARD` (in `trainui/data.py`) | **shared** | check-level fact: which canonical sections a check queries. Tied to the check implementation, not the payer. |
| `REWRITABLE_STANDARDS` (in `trainui/data.py`) | **shared** | a medico-legal boundary (what may be mechanically rewritten), not payer policy. |

Target layout:
```
rules/
  section_synonyms.yaml          # SHARED (stays at top level)
  optum_commercial/
    ruleset.yaml
    applicability.yaml
    thresholds.yaml
    payer_text.yaml              # was STANDARD_TEXT
    rewrites.yaml
    corpus.json
    prompts/<id>.md
  medicaid_co/                   # the new payer, authored in §8
    ruleset.yaml
    applicability.yaml
    thresholds.yaml
    payer_text.yaml
    prompts/<id>.md
    corpus.json
```

---

## 5. The migration surface (the touch list)

Today the set of 49 standards is enumerated in these places. Each must be made
to **derive from the active ruleset** rather than from a module global.

1. **`compliance/applicability.py`** — `MATRIX` → per-ruleset applicability.
   **Also fix the latent bug here:** `applies()` consults the YAML overrides but
   `get_applicable_standards()` reads `MATRIX` only, so they disagree (and the
   empty-dict rows for `B2`/`K2` make `get_applicable_standards` silently return
   nothing for them). Route **both** through the ruleset's single resolved
   applicability source so this divergence dies instead of being duplicated per
   ruleset. **Make the empty-dict resolution a conscious choice, not an
   accident:** `B2`/`K2` are intended to always fire as `manual_review`, but the
   empty-dict rows currently cause them to be *dropped*. Decide explicitly
   whether unification resolves empty-dict to "run as manual_review for all doc
   types" (the apparent intent) or "omit" — and encode that decision in the
   ruleset applicability resolver. Unifying the two functions must not silently
   mean "they now agree on dropping two standards the payer expects."
2. **`compliance/runner.py`** — `ALL_CHECKS`, `_CHECK_MAP`, `run_note`,
   `run_batch` → use `ruleset.checks()` and `ruleset.applies(...)`.
3. **`trainui/data.py`** — holds a **second, duplicate** `ALL_CHECKS` plus
   `STANDARD_TITLES` / `STANDARD_ORDER` / `STANDARD_TEXT` /
   `REWRITABLE_STANDARDS` / `SECTIONS_FOR_STANDARD`. (Verified: the two
   `ALL_CHECKS` lists are identical, 49 entries each.)
4. **`compliance/config.py`** — `RULES_DIR` (one flat dir) →
   `rules_dir_for(ruleset_id)`; the mtime cache keys stay per-file so live
   reload still works.
5. **Selection plumbing** — `--ruleset` on `python -m compliance audit` and on
   `trainstandards.py` (default `optum_commercial`); a UI dropdown; the active
   ruleset id carried into evaluate, rewrite, and regression.
6. **Reports + rewrite audit manifest** — record *which ruleset* produced each
   verdict (`findings.jsonl`, CSV, HTML, and the `.rewrite.json` manifest). This
   is a defensibility requirement: a stored verdict is meaningless without the
   payer rules it was judged against.

### 5.1 Sequencing rule (critical)

**Unify the two `ALL_CHECKS` first, *then* add the ruleset dimension.** If
`trainui/data.py` and `runner.py` are each parameterized by ruleset separately,
the result is `2 × N` copies. Collapse both to consume *one* registry/manifest,
and only then introduce the ruleset selection. Order matters here.

---

## 6. Selection granularity — per-run vs per-document

A provider bills across payers, so a single input directory may legitimately mix
Medicaid and Commercial notes. This raises a question the task implies but
doesn't answer, so it is surfaced here rather than decided silently:

- **Per-run (recommended for v1):** one `--ruleset` flag / one UI selection
  applies to the whole batch. Simple, predictable, matches the common case where
  a user is auditing one payer's records at a time.
- **Per-document (future):** tag each PDF/note with its ruleset (e.g. a sidecar
  or a manifest mapping filename → ruleset) and evaluate each against its own.

**Decision:** ship **per-run** in v1. But design the `Ruleset` plumbing so the
active ruleset is passed *as a parameter* down to `run_note` / `evaluate_pdf`,
not read from a global — that leaves a clean seam to make it per-document later
without another refactor.

---

## 7. Inheritance (`extends`) — a named decision

Medicaid rules are often "Commercial, but with these deltas." Two options:

- **Explicit full manifests** — every ruleset lists all its standards. Simple to
  read, but duplicates ~49 entries per payer and drifts over time.
- **Single-level `extends`** — a ruleset names a base and overlays only its
  deltas (changed applicability, added/removed standards, overridden prompts,
  `impl` overrides). No duplication; the diff *is* the payer difference.

**Recommendation:** allow **one-level `extends` only** (no chains, no diamonds).
Resolution stays dead-simple and debuggable: load base, apply this ruleset's
overlay, done. Reject manifests that `extends` a ruleset that itself `extends`
something — fail loudly at load time. This is presented as a decision to
confirm, not a baked-in requirement; if simplicity is preferred over
de-duplication, explicit manifests are acceptable for v1.

---

## 8. Implementation sequence (each step gated by identical verdicts)

Mirrors the discipline of the fixtnpdf and trainstandards-refactor plans: every
step leaves the system runnable and is gated by the §1 invariant.

1. **Introduce the `Ruleset` abstraction with exactly one ruleset = today.**
   Build `compliance/ruleset.py` (loader + `Ruleset` object + registry of
   available ruleset ids). Unify the duplicate `ALL_CHECKS` so `runner` and
   `trainui` both consume the resolved ruleset. Default ruleset reproduces the
   current `ALL_CHECKS` / titles / text / MATRIX exactly.
   **Gate:** `python -m compliance audit --input sourcedocs/` yields byte-
   identical `findings.*` before vs. after.
2. **Move the flat `rules/*.yaml` into `rules/optum_commercial/`** (with a
   back-compat shim so an old flat `rules/` still loads, or a one-time migration
   step). Keep `section_synonyms.yaml` shared at top level.
   **Gate:** identical verdicts.
3. **Thread `--ruleset` and the UI selector**, defaulting to `optum_commercial`.
   Carry the active id into evaluate / rewrite / regression / reports.
   **Gate:** identical verdicts with the default selected.
4. **Author the Medicaid ruleset** — a `medicaid_co/ruleset.yaml` (optionally
   `extends: optum_commercial`) + applicability/threshold/prompt/text deltas +
   only the handful of `impl`-overridden checks, authored through the existing
   **Tier-1 (config), Tier-2 (prompts), Tier-3 (codegen handoff)** editors in
   the training UI. **This is where the payoff lands** — and it requires no
   change to the shared checks. The `impl` override belongs here, in the
   *Medicaid* manifest, pointing at a class under
   `compliance/checks/rulesets/medicaid_co/` (§3.1):

   ```yaml
   # rules/medicaid_co/ruleset.yaml
   extends: optum_commercial
   standards:
     - id: E6
       title: "Goal time frames"
       impl: "compliance.checks.rulesets.medicaid_co.e_treatment_plan.CheckE6Medicaid"
     # everything else inherited from optum_commercial via `extends`
   ```

Steps 1–3 are a pure refactor (zero behavior change). Step 4 is the new
capability.

---

## 9. UI changes (training system)

The training UI must make the active ruleset visible and switchable, because
"training the standards" now means "training *a particular payer's* standards."

- **Ruleset selector** in the top bar (dropdown populated from the ruleset
  registry), defaulting to `optum_commercial`. Changing it re-evaluates the
  current PDF against the selected ruleset.
- The active ruleset id is sent with every `/api/evaluate`, `/api/rewrite/*`,
  and `/api/regression/*` call, and is shown in the card dialog and the
  generated change-request artifacts (so a Tier-3 handoff says *which* payer's
  rule is being changed).
- The **regression corpus is per-ruleset** (§4): pinning a verdict pins it under
  the active ruleset; running regression runs against that ruleset's corpus.
- The rewrite **audit manifest** records the active ruleset id.

No new editor tiers are needed — Tiers 1/2/3 already exist; they now write into
`rules/<active_ruleset>/` instead of the flat `rules/`.

---

## 10. Out of scope / explicitly avoided

- **Plugin / entry-points discovery framework.** Rulesets are loaded from a
  known `rules/` subtree via a small registry — not auto-discovered Python
  plugins. Keep it a registry indirection, not a framework.
- **Multi-level inheritance / mixins.** One-level `extends` max (§7).
- **Per-document ruleset selection** in v1 (seam left for it; §6).
- **Forking `classify.py` or `section_synonyms.yaml`** — these are
  payer-independent and stay shared (§4).
- **Changing any existing check's logic.** The default ruleset must be behavior-
  identical; new payers add overrides, never edit shared checks.
- **Renaming the concept.** Use **"ruleset"** consistently (not "profile,"
  which is overloaded).

---

## 11. Verification (definition of done)

1. With no `--ruleset` flag, `python -m compliance audit --input sourcedocs/`
   and the training UI produce **identical verdicts** to pre-refactor (the §1
   invariant). This is the single most important test.
2. `--ruleset optum_commercial` is equivalent to the default.
3. A second ruleset (`medicaid_co`) loads, appears in the UI dropdown and the
   audit CLI, and evaluates `sourcedocs/` producing verdicts that differ *only*
   where its manifest/config/`impl` deltas say they should.
4. The applicability source is unified: `applies()` and
   `get_applicable_standards()` (or their ruleset-method successors) agree for
   every `(standard_id, doc_type)` — including `B2`/`K2`.
5. There is exactly **one** `ALL_CHECKS`-equivalent registry; `trainui` no longer
   holds a duplicate.
6. Reports and the rewrite audit manifest record the ruleset id that produced
   each verdict.
7. The regression corpus is stored and run per-ruleset.
```
