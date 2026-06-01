# Interactive Rule Editing for the Standards Trainer — Design Plan

> Status: design only. No code in this document. This plan extends
> `trainstandards.py` (see [trainstandards.md](trainstandards.md)) with the
> ability to change *how a standard is judged* from inside the training loop,
> instead of hand-editing Python and restarting the server.

## 1. Context — the problem we are solving

`trainstandards.py` today is a read-only inspector: you can see a verdict, its
rationale, the excerpts, and (for judgment checks) the exact question the engine
posed to the judge. But the moment you decide *"this rule is wrong"*, the loop
breaks — you leave the tool, open `compliance/checks/*.py` in an editor, change
code by hand, and restart. "Training the standards" is exactly this edit loop,
and it is currently slow, manual, and disconnected from the evidence in front of
you.

The user has floated two mechanisms for closing the loop:

- **(A)** an LLM writes new rule code that is **dynamically swapped** into the
  running engine; or
- **(B)** the tool **emits a prompt**, the server is stopped, the prompt goes
  into VSCode / Claude Code, the new rule code is generated there, and the
  engine picks it up on restart.

Both are about *code*. The central argument of this plan is that **most rule
modifications are not code changes at all** — they are data or prompt changes —
and that recognizing this collapses most of the risk. We therefore propose a
**tiered design** where the dangerous, powerful code-swap path is the last
resort, not the default.

**Bottom line, up front (the user's A-vs-B question):** prefer **option B**
(emit a change request → generate code in Claude Code/VSCode → commit to git →
reload) as the **default** code path (this is Tier 3a below). Use **option A**
(in-process dynamic hot-swap, Tier 3b) only as an opt-in experimental mode and
only behind a sandbox + an Apply gate + a regression run. And note that for the
majority of edits you will not reach either: synonyms, keywords, the
applicability matrix, thresholds, and judge prompts are *data*, editable live
and safely (Tiers 1–2).

## 2. How a standard is judged today

Every standard is a `Check` class (`CheckA1`, `CheckD1`, …) in
`compliance/checks/*.py` exposing `run(note, judge, bundle) -> CheckResult`.
Inside that one method there are really **three layers** mixed together:

| Layer | What it is | Where it lives today | Nature |
|---|---|---|---|
| **Applicability gate** | "does this standard apply to this note type?" | `compliance/applicability.py` `MATRIX` + an early `if note.note_type …` guard inside the check | **data** + a little control flow |
| **Rule path** | deterministic detection: section presence, regex/keyword matches, header-field checks, thresholds | constants + `if`/`for` logic inside each check, plus shared tables in `extract/sections.py` and `extract/medications.py` | **data tables** wrapped in **Python control flow** |
| **Judge path** | when rules can't decide, build a `question` + `context` and call `judge.evaluate(...)` | a `question=` string literal inside the check; shared system prompt in `compliance/judges/claude.py` (`_SYSTEM`) | **prompt text** embedded in code |

Concrete examples of the "data" hiding inside the rules:

- **Section synonyms** — `SECTION_SYNONYMS` in `compliance/extract/sections.py`
  maps `presenting_problem → ["presenting problem", "reason for visit",
  "chief complaint", …]`. Most "this check can't find the section" failures are
  fixed by adding a synonym, not by changing logic.
- **Keyword / regex tables** — e.g. `RISK_KEYWORDS` and
  `RE_SUBSTANCE_CATEGORIES` in `d_assessment.py`, `TELEHEALTH_MODS` in
  `f_progress.py`, `RE_NEGATED_ALLERGY` in `c_medication.py`.
- **The applicability matrix** — `MATRIX` (R / C / not-applicable per doc type).
- **Thresholds** — e.g. the 24-hour late-entry window (`timedelta(hours=24)`)
  in `b_entry.py`.
- **Judge questions** — the `question=` strings (e.g. the MSE-dimensions
  question in `CheckD1`, the SMART-criteria question in `CheckE5`). Today there
  is **no per-standard prompt template** — the prompt is `(_SYSTEM)` +
  `(question built in code)`.

**Implication:** if we lift this data out of the code into editable config, a
large fraction of "rule changes" become **safe, instant, no-code-execution
edits**. Only genuinely new *control flow* needs code generation.

## 3. Taxonomy of "rule changes" — by difficulty and risk

| # | Change type | Example | Mechanism needed | Risk |
|---|---|---|---|---|
| 1 | Add/edit a **section synonym** | teach `presenting_problem` to match "reason for referral" | edit config table | none (data) |
| 2 | Add/edit a **keyword / regex / code set** | add `POS 10` to telehealth modifiers; add a risk keyword | edit config table | low (a bad regex over-matches — caught by regression set) |
| 3 | Change **applicability** | make A2 conditional, not required, for intakes | edit matrix config | none (data) |
| 4 | Change a **threshold** | late-entry window 24h → 72h | edit config value | none (data) |
| 5 | Edit a **judge prompt** | tighten the SMART-goals question; add few-shot examples | edit prompt config; re-run note via ClaudeJudge | low (text; cost/PHI of the LLM call) |
| 6 | Change **rule control flow** | "pass only if MSE has ≥7 of 10 dimensions"; combine two sections with new logic | generate/modify Python | **high** (arbitrary code, determinism, audit) |

Rows 1–5 are **config/prompt** edits. Row 6 is the only one that is truly
*code*. The two mechanisms the user proposed (A and B) are both about row 6.

## 4. Proposed design — a tiered loop

### Tier 1 — Editable config (rows 1–4). No code execution.

Lift the tunable data into versioned config files (e.g. a `rules/` directory:
`rules/section_synonyms.yaml`, `rules/keywords.yaml`, `rules/applicability.yaml`,
`rules/thresholds.yaml`). The checks must read these tables **at call time**
instead of from import-time module constants (today `SECTION_SYNONYMS`,
`RISK_KEYWORDS`, the compiled regexes, etc. are bound once at import, and
`trainstandards.py` iterates a single module-level `ALL_CHECKS` list of check
singletons — so config is *not* picked up for free). Once the checks consult
config at call time, each re-evaluation reads the latest values and edits go
**live with no restart** — a small, well-contained change to how the tables are
loaded, not a rearchitecture.

UI loop (inside the card's existing dialog):

1. The dialog already shows the rule inputs (extracted sections, header fields)
   and, when relevant, which synonym/keyword table drove the verdict.
2. Add an **"Edit rule data"** affordance that surfaces the *specific* table the
   check used (e.g. the `presenting_problem` synonym list for a D1 failure).
3. Edit → Save (writes the YAML) → **auto re-evaluate this note** → show a
   **before/after verdict diff** for the card.

This single tier covers the majority of day-to-day "training" and is completely
safe.

### Tier 2 — Editable judge prompts (row 5). No code execution.

Promote the per-standard judge `question` (and optionally a per-standard system
preamble / few-shot block) into config (`rules/prompts/<standard>.md`). The
check loads its prompt template from config instead of an inline string.

UI loop:

1. In a judgment card's dialog, the **Judge path** panel (already showing the
   recorded question + context + answer) becomes **editable**.
2. Edit the prompt → **"Test against this note"** runs a *single* live
   `ClaudeJudge` call with the new prompt over the same context → show the new
   verdict/rationale beside the old.
3. Keep / revert. On keep, the prompt is written to config (versioned).

This is the "set of prompts" idea — but kept *inside* the tool, with the note's
real context, rather than copy-pasting into VSCode. Note the PHI implication: a
live test call sends note text to the API (gated by the BAA decision, Q-LLM-2;
support a redaction / synthetic-note mode).

### Tier 3 — Rule code changes (row 6). The fork the user is asking about.

When a change genuinely needs new Python control flow, there are two strategies.
We present both and recommend a default.

#### Tier 3a — Assisted offline codegen (the "prompt → VSCode/Claude Code" path) — **recommended default**

The tool assembles a precise, self-contained **change request** and hands it off
to the developer's existing coding agent (Claude Code / VSCode), which edits the
real `compliance/checks/*.py` under git. The engine reloads the change.

What the generated change-request artifact contains (this is the high-value
part — it removes the human's transcription burden):

- the **standard text** verbatim (from `Record Standards.txt`),
- the **current check source** (read from the `.py`),
- the **note's structured inputs** the dialog already has (extracted sections,
  header fields) — *not necessarily raw PHI*,
- the **observed vs. desired verdict** and a one-line human description of the
  fix,
- **hard constraints**: keep the `run(note, judge, bundle)` signature, modify
  only the rule path, return a `CheckResult`, don't broaden applicability.

Delivery: write to `rule_requests/<standard>_<timestamp>.md` and/or copy to
clipboard; optionally open it. The developer runs it through their agent, which
writes the new code; git captures the diff; the engine reloads (see §6 reload
mechanics) or restarts.

Why this is the default:

- **Auditability / reproducibility** — the audit engine's entire value is a
  stable, git-tracked verdict. Code that lives only in server memory destroys
  that. 3a keeps every rule change as a reviewable diff.
- **Correctness** — a human reviewing the diff catches the "this regex now
  matches half the corpus" error *before* it pollutes a 5,000-finding batch.
- **PHI** — the request can carry the *extracted structure* and the standard
  text rather than raw note text, and the human controls exactly what is shared.
- **Low machinery** — no sandbox, no resource limits, no rollback engine; it
  reuses the coding agent you already trust.

Cost: a slower loop (a handoff, not an in-tool click).

#### Tier 3b — In-process hot-swap of generated code — powerful, conditional

The tool asks an LLM to generate replacement rule logic, loads it dynamically,
swaps it into the live registry, and re-runs the note instantly — the "magic"
loop. This is genuinely attractive for iteration speed, but it is only safe and
correct if **all four** of these hold:

1. **Small, pure unit.** Generate not a whole `Check` but a **pure predicate**
   over a **read-only, PHI-minimized `NoteView`** (see §5):
   `evaluate(view) -> (verdict, rationale, excerpts)`. Small surface = reviewable
   and sandboxable.
2. **Sandboxed execution.** Run in a restricted namespace: no imports beyond an
   allowlist, no filesystem/network, a wall-clock timeout, caught exceptions →
   `manual_review`.
3. **Write-through to disk + explicit Apply gate.** The generated predicate is
   *persisted as a versioned artifact* the instant it is created and only enters
   the audit path on an explicit human **Apply** (which produces a git-visible
   change). Never auto-persist generated code into verdicts.
4. **Regression on Apply.** Applying a code change reruns the eval corpus (§6)
   and shows which notes flipped, so you can't silently overfit to the one note
   on screen.

If you are not prepared to build items 2–4, **do not** build 3b; 3a delivers
~90% of the benefit at ~10% of the risk. Recommendation: ship Tiers 1–2, make
3a the primary code path, and design the registry/`NoteView` so 3b can be added
later **behind those four conditions** as an opt-in "experimental" mode.

## 5. Enabling refactor (optional, but it makes Tier 3 tractable)

Today a `Check.run` blends four concerns (applicability gate, section lookup,
rule logic, judge fallback). The cleaner shape that makes rules *modifiable*:

- A check declares **what inputs it needs** (which sections / header fields).
- A check exposes a **pure predicate** over a `NoteView` — a read-only,
  serializable projection of the note (sections dict, header fields, page
  texts), ideally PHI-minimized for the LLM-facing paths.
- A check carries an **optional judge spec** (a prompt template from Tier-2
  config).

With rules expressed as pure predicates over a defined view, *both* config
tuning and code-swap shrink to a tiny, sandboxable surface. This refactor is
**not required** for Tiers 1–2 and can be done incrementally (start with the few
checks you most want to train).

## 6. Cross-cutting requirements (apply to every tier)

- **Persistence & versioning.** Every change — config, prompt, or code — is
  written to disk under git. Verdicts must stay reproducible; an in-memory-only
  rule is a non-starter for an audit tool. Record *who changed what and why*
  (a short rationale per change), echoing the provenance you'd want in an audit.
- **Regression corpus — the most important safeguard.** Interactive tuning
  against the single note on screen **overfits**. We need a small set of notes
  with known-expected verdicts (this is the unanswered Q-LLM-3 in
  `compliance_plan.md`). Any change — synonym, keyword, prompt, or code — reruns
  the corpus and reports **deltas**: which notes flipped pass↔fail↔review. The
  trainer should refuse to "Apply" a change that regresses pinned cases without
  explicit override. Without this, every tier is a foot-gun.
- **PHI / BAA.** Tier-2 prompt tests and any Tier-3 LLM call send note text
  outward. Support a **redaction / synthetic-note** mode, and gate live LLM
  calls on the BAA decision (Q-LLM-2). Prefer sending extracted structure +
  standard text over raw notes where possible (especially for codegen).
- **Reload mechanics.**
  - *Config/prompts (Tiers 1–2):* trivial — read the file inside the
    evaluation, so each re-evaluate picks up the latest. No restart.
  - *Code (Tier 3):* `importlib.reload` the affected `compliance/checks/*`
    module and rebuild the `ALL_CHECKS` registry (note: `trainstandards.py` and
    `compliance/runner.py` each hold their own `ALL_CHECKS` list — a reload must
    rebuild the one the trainer uses). Offer a **"Reload rules"** button and/or
    a file-watch on `rules/` + `compliance/checks/`.
- **Concurrency.** Hot-swapping in a live server is racy under concurrent
  requests. For a single-user training tool this is acceptable; document it and
  serialize evaluations if needed.

## 7. UI interaction model (what changes in `trainstandards.py`)

The existing per-card dialog already has the right anatomy (applicability,
verdict, evidence, judge path, rule inputs). Rule editing slots in as new
sections/buttons:

- **Edit rule data** (Tier 1): inline editor for the specific synonym/keyword/
  threshold/matrix entry that drove the verdict → Save → auto re-evaluate → show
  before/after for this card.
- **Edit & test prompt** (Tier 2): make the Judge-path panel editable → "Test
  against this note" → side-by-side old vs. new verdict.
- **Generate code-change request** (Tier 3a): assemble and export the handoff
  artifact (file + clipboard).
- **(Experimental) Propose & hot-test rule** (Tier 3b, if built): generate a
  sandboxed predicate, show old vs. new verdict, require **Apply** (which writes
  to disk + runs the regression corpus).
- **Run regression** + **Reload rules** controls at the top of the right pane.

## 8. Recommended build order

1. **Tier 1 (config tables) + persistence under git** — biggest value, lowest
   risk; turns the most common failures into instant safe edits.
2. **Regression corpus + delta view** — build this early; it is the safety net
   that makes *all* later tiers trustworthy. (Bootstraps Q-LLM-3.)
3. **Tier 2 (editable judge prompts) + live single-note test** — high leverage
   for the genuinely judgment-based standards.
4. **Tier 3a (assisted offline codegen handoff)** — the pragmatic answer to the
   user's question; pairs the tool's evidence with the coding agent + git you
   already have.
5. **Optional: enabling refactor (`NoteView` + pure predicates)**, then **Tier
   3b (sandboxed hot-swap)** behind the four conditions — only if the fast
   in-tool code loop proves worth the sandbox/rollback machinery.

## 9. Risks & open questions

- **Overfitting to the visible note** — mitigated only by the regression corpus
  (§6). This is the dominant risk of *any* interactive tuning.
- **Config vs. code boundary (OPS-2 in `compliance_plan.md`)** — this plan
  answers it: push the *data* to config (Tiers 1–2), keep *control flow* in code
  (Tier 3). Worth confirming with stakeholders.
- **PHI off-machine (Q-LLM-2)** — needs the BAA decision before Tier-2/3 LLM
  calls run on real notes; redaction/synthetic mode is the interim.
- **Eval corpus source (Q-LLM-3)** — where do known-good/known-bad annotated
  notes come from? The trainer can *bootstrap* this: every "keep" decision pins
  the note's expected verdict into the corpus.
- **Trust in generated code (3b)** — without the sandbox + Apply gate +
  regression, generated rules can silently corrupt a batch. This is why 3a is
  the default.

## 10. Out of scope (for this plan)

Multi-user/role-based editing and approval workflows; a full rule-versioning UI
with branching; automatic prompt optimization; and editing the ingestion /
section-extraction *engine* itself (as opposed to its synonym tables).
