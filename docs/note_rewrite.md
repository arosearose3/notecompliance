# Plan — Note Rewrite: authoring PDF modifications in `trainstandards.py`

**Status:** design document. No code in this change.
**Audience:** the implementer of the next phase of `trainstandards.py`.

---

## 1. BLUF

`fixtnpdf.py` already performs exactly one PDF rewrite: it corrects the rendering
provider's credential (Intern / LPCC / LPC) and license ID in the header and
signature spans. That is a *specific instance* of a general operation — "find
target text in a PDF, replace it, write a corrected copy without touching the
original."

This plan proposes a **refactor**, not a bolt-on:

1. **Extract** the rewrite engine that lives inside `fixtnpdf.py` into a shared
   library, `compliance/rewrite/`, defined around a single abstraction — a
   **rewrite action** = *locator* + *transform* + *applier*.
2. **Re-express** the title fix as the first registered action against that
   library, so `fixtnpdf.py` becomes a thin CLI over it (behavior unchanged).
3. **Surface** rewrite authoring in `trainstandards.py`: from a failing standard
   card, the user can preview, configure, and apply a mechanical correction to
   the note, then re-evaluate to confirm the card flips and nothing else
   regresses.

The design deliberately mirrors the repo's existing **tiered rule-editing**
model (`docs/rule_editing.md`): simple rewrites are declarative config; complex,
data-driven rewrites produce a **codegen-handoff artifact** exactly like
`_build_request_artifact`. Consistency with what already exists is the goal.

This document also states, up front, three boundaries that constrain the design
(§7): the viewer can't capture clicks on the PDF, only a narrow class of
standards is mechanically rewritable, and we are altering signed clinical
records and therefore need explicit guardrails.

---

## 2. What `fixtnpdf.py` actually does (the worked example)

The title fix is the reference implementation for everything below. Decomposed,
it is already a locator + transform + applier — it just isn't named that way:

| Phase | In `fixtnpdf.py` today | Generalized name |
|---|---|---|
| **Locate** | `_find_affected_spans` / `_find_insert_spans` walk `page.get_text("dict")` and return spans whose text contains `"{clinician}, {old_title}"` (or the bare name), with their `rect`, `origin`, `size`. | **Locator** — given a page, return the spans to change. |
| **Transform** | `_substitute_span_text` / `_clean_signature_span` compute the replacement string; the *decision* of what the new credential is comes from `compute_credential(session_date, provider)` driven by the licensure CSV. | **Transform** — given a located span + a data source, produce its replacement text. |
| **Apply** | `apply_corrections`: copy selected pages into a fresh PDF, `add_redact_annot(rect, fill=white)` + `apply_redactions`, then `insert_text(origin, new_text, "helv", size)`. Originals never modified; output written to a separate dir. | **Applier** — white out the old span rect, reinsert the new text at the same origin. |

Key mechanical facts the engine depends on, that the refactor must preserve:

- **Two PDF libraries, by role.** Reading/structure is `pdfplumber`
  (`compliance.ingest.split_notes`). **Span geometry — bbox, origin, font size —
  exists only on the PyMuPDF (`fitz`) side.** Any "show me / pick the target
  span" UI is therefore fitz-sourced. This makes `fitz` a new dependency of
  `trainstandards.py` (see §8).
- **Redact-then-reinsert, not edit-in-place.** PDFs have no editable text model;
  the engine paints white over the old span's rectangle and draws new text at the
  old origin in Helvetica at the captured size. Replacement text that is *wider*
  than the original can overrun; the title fix avoids this by keeping
  replacements short (`#NNNNN`, not `License CO NNNNN`). The general engine must
  treat overflow as a real risk and surface it in preview (§7.3, §9).
- **Small-caps normalization.** `_normalize_text` maps Unicode small-caps glyphs
  to ASCII so Helvetica can render them. This is engine-level, not title-specific
  — it moves into the shared applier.
- **The originals invariant.** `fixtnpdf` reads from `--input`, writes to
  `--output`, and *never* overwrites a source file. This is a medico-legal
  property, not a convenience (§7.4). The shared engine enforces it; the UI
  cannot bypass it.

---

## 3. The abstraction: a rewrite action

```
RewriteAction
  ├─ id            : str         # e.g. "provider_title", stable identifier
  ├─ label         : str         # human title for the UI
  ├─ locate(page, note, params) -> list[TargetSpan]
  │     # walk fitz get_text("dict"); return spans to change with rect/origin/size/font
  ├─ transform(target, note, params, data) -> str | None
  │     # compute the replacement string; None = leave this span unchanged
  └─ scope        : "note" | "page" | "document"
                                 # which pages the action may touch for one note
```

Supporting types (these formalize dicts that already exist informally in
`fixtnpdf._find_affected_spans`):

```
TargetSpan   = { page_index, rect, origin, size, font, old_text }
RewritePlan  = ordered list of (TargetSpan, new_text) across a note's pages
RewriteResult= { output_path, spans_changed, manifest }   # see §9 audit manifest
```

**The applier is shared and action-agnostic.** It consumes a `RewritePlan` and
performs the redact + reinsert + save-to-output exactly as `apply_corrections`
does today. Actions never touch `fitz` writes directly; they only *locate* and
*transform*. This is what keeps a new action small and keeps the dangerous part
(modifying the PDF bytes) in one audited place.

### The title fix re-expressed as an action

- `id = "provider_title"`, `scope = "note"`.
- `locate` = the existing `_find_affected_spans` + `_find_insert_spans` logic,
  parameterized by clinician name (from `note.header.clinician`).
- `transform` = `compute_credential(note.header.service_date, provider)` →
  feed `_substitute_span_text`. `data` = the licensure CSV (plus supervisors).
- The supervisor fix (`_find_supervisor_span_fixes`) is a *second* registered
  action, `id = "supervisor_credential"`, proving the registry holds more than
  one action on day one.

`fixtnpdf.py main()` becomes: load CSVs → register these two actions → run them
through the shared applier. The CLI's output, flags, and behavior are byte-for-
byte unchanged; only the internals move. This is the regression test for the
refactor: `fixtnpdf` on `sourcedocs/` must produce identical output PDFs before
and after.

---

## 4. Two tiers of authoring (mirrors `docs/rule_editing.md`)

Rule editing already distinguishes *config you can change live* (Tier 1) from
*logic that needs new code via a handoff artifact* (Tier 3a). Rewrite authoring
uses the same split, because the same complexity gradient applies.

### Tier R1 — Declarative field rewrites (config, no code)

For rewrites that are **find-a-known-field, substitute-a-value**, the user
authors them entirely in the UI; they persist as YAML under `rules/` (like
`section_synonyms.yaml`) and load via the mtime cache (`compliance/config.py`),
so no restart is needed.

A Tier-R1 rewrite is expressed declaratively:

```yaml
# rules/rewrites.yaml
- id: telehealth_modifier
  label: "Add telehealth delivery statement"
  match:
    section: signature          # or: header_field, or a literal anchor string
    pattern: "signed this note"
  replace:
    template: "{name}, {credential}, telehealth session, signed this note"
  applies_to: [progress, consultation]
```

The generic locator interprets `match` (anchor string / section / header field),
and the generic transform interprets `replace.template` against note fields. No
Python is written. This covers: appending a boilerplate phrase, correcting a
mislabeled field, normalizing a credential string, stamping a fixed value into a
known location.

**The title fix is intentionally *not* Tier R1** — its replacement value depends
on a date comparison against a CSV, which a template can't express. That is the
boundary between the tiers.

### Tier R3 — Codegen-handoff rewrite actions (data-driven)

When the transform needs real logic (date math, CSV lookup, conditional
formatting, multi-span reconstruction like `_clean_signature_span`), the UI does
**not** try to author Python in-process. It emits a **change-request artifact**
— the exact pattern already used for rule changes
(`trainstandards._build_request_artifact`, `/api/generate-request`).

The artifact for a rewrite action contains:

- The action `id`, label, intended scope, and which standard it remediates.
- The **target spans** the user selected, captured from `get_text("dict")`:
  their `old_text`, page index, and surrounding context (non-PHI-minimized).
- The **desired replacement** the user typed or described.
- The **data source** the transform should consult (e.g. "licensure CSV, column
  X") if any.
- The hard constraints (mirroring the rule artifact's §"Hard constraints"):
  reuse the shared applier, never modify originals, keep replacements within the
  original span width where possible, register under `compliance/rewrite/actions/`.

The user takes that artifact to a coding session (VS Code + Claude), the action
is implemented and registered, the server reloads (`/api/reload`), and the new
action appears in the UI. This is the same offline-codegen loop the project
already chose for rules — no hot-swap, no in-process `exec`.

---

## 5. UI in `trainstandards.py`

The existing UI is three panes: PDF list (left), native PDF viewer (center),
standard cards / accordion (right), with a drill-down dialog per card. Rewrite
authoring attaches to the **card dialog** — the place the user is already looking
when a standard fails.

### 5.1 Entry point: the card dialog gains a "Rewrite" affordance

When a card's verdict is `fail` (and the standard is in the *mechanically
rewritable* allowlist — §7.2), the dialog shows an **"Author a rewrite…"**
button next to the existing "Generate change request" affordance. Cards for
non-rewritable standards (missing MSE, absent presenting problem) do **not** show
it; they show a short note explaining that the remedy is clinical content, not a
mechanical edit (§7.2).

### 5.2 The rewrite authoring panel

Opening it reveals a focused authoring view (a larger modal or a right-rail
drawer), with four regions:

1. **Pick the target span(s).** Because the center viewer is a native PDF iframe
   that *cannot report click coordinates* (§7.1), we do **not** ask the user to
   click on the rendered PDF. Instead the server enumerates the note's spans via
   `fitz.get_text("dict")` and returns a **selectable span list** — each entry
   shows the span's text and page number, grouped by page, with the header/
   signature spans surfaced first (they're the usual targets). The user checks
   the spans to rewrite. Optionally we render a lightweight page thumbnail with
   the chosen span's bbox highlighted, drawn server-side from the known `rect` —
   this is display-only, still no click capture needed.

2. **Choose the action.**
   - *Existing registered action* (e.g. `provider_title`) → pick it, supply its
     params (the action declares them); skip straight to preview.
   - *New Tier-R1 declarative rewrite* → fill the `match`/`replace` form (§4);
     it's saved to `rules/rewrites.yaml`.
   - *New Tier-R3 action* → describe the desired transform; this routes to the
     **change-request artifact** (§4), not to an apply.

3. **Preview / diff.** The server builds the `RewritePlan` and returns, per
   target span, `old_text → new_text`, plus an **overflow flag** if the
   replacement is wider than the original span (§7.3). Nothing has been written
   yet. The diff is the approval gate.

4. **Apply.** On explicit confirm, the shared applier writes a corrected PDF to
   the **output directory** (never over the source), and returns the audit
   manifest (§9). The center viewer can then load the rewritten copy so the user
   sees the result.

### 5.3 Re-evaluate to confirm (close the loop)

After an apply, the UI offers **"Re-evaluate rewritten note."** This runs the
compliance engine on the *output* PDF and shows the card deltas. Success means:

- the targeted standard's card flips from `fail` to `pass` (or to the intended
  verdict), **and**
- no other card regresses.

This reuses the **regression corpus** mechanism already in the repo
(`/api/regression/run`, `rules/corpus.json`): the post-rewrite evaluation is
checked against pinned expected verdicts so a rewrite that fixes one thing and
breaks another is caught immediately, not silently shipped.

---

## 6. Routes added to `trainstandards.py`

All new routes follow the existing conventions in `create_app`:

| Route | Method | Purpose |
|---|---|---|
| `/api/rewrite/actions` | GET | List registered rewrite actions (id, label, params, applies_to). |
| `/api/rewrite/spans?pdf=&note=` | GET | Enumerate selectable spans for a note via `fitz.get_text("dict")` (text + page + bbox). |
| `/api/rewrite/preview` | POST | Build a `RewritePlan`; return per-span `old→new` diff + overflow flags. **No write.** |
| `/api/rewrite/apply` | POST | Run the shared applier; write to output dir; return audit manifest + rewritten-PDF path. |
| `/api/rewrite/config` | GET/POST | Read/write `rules/rewrites.yaml` (Tier R1 declarative actions). |
| `/api/rewrite/generate-request` | POST | Emit the Tier-R3 change-request artifact (parallels `/api/generate-request`). |
| `/pdf/output/<name>` | GET | Serve a rewritten PDF from the output dir so the viewer can show the result. |

CLI gains `--output <dir>` (defaulting like `fixtnpdf` does) so the UI knows
where corrected copies go; `--judge`, `--no-ai`, `--input` are unchanged.

---

## 7. Boundaries and guardrails (read before implementing)

These are not optional caveats; each one shapes a design decision above.

### 7.1 The native viewer cannot capture clicks on the PDF

The center pane is a browser-native `<iframe>` rendering the PDF; the original
`trainstandards` plan deliberately kept `pdf.js` **out of scope**. A native
iframe gives us no coordinates for "where did the user click on the page." So a
UX of *click the text in the PDF to select it* does not work with the current
viewer. The design resolves this by selecting targets from a **server-enumerated
span list** (§5.2.1) sourced from fitz, not from clicks. If a future phase wants
true click-on-PDF authoring, that requires adopting `pdf.js` — call it out as a
separate, larger decision, not an assumed capability here.

### 7.2 Only a narrow class of standards is mechanically rewritable

`trainstandards` evaluates 47 standards, and the obvious-looking move is "every
failing card gets a Fix button." That is wrong and must be designed against.
A PDF rewrite can correct **administrative metadata and boilerplate that exists
or is mislabeled**: provider title/credential, license ID, a delivery-method
statement, a mis-formatted date field, a present-but-mislabeled section heading.
A PDF rewrite **cannot and must not** manufacture **absent clinical content** —
a missing Mental Status Exam, an absent presenting problem, an unwritten risk
assessment. Synthesizing that would be fabricating the medical record. The UI
therefore maintains an explicit **rewritable-standard allowlist**; cards outside
it show no rewrite affordance and a one-line explanation that the remedy is
clinical documentation, not an edit. State this allowlist in code, near the card
rendering, so the boundary is visible and reviewable.

### 7.3 Replacement-width overflow is a real failure mode

Because the applier paints over the old span rect and draws new text at the same
origin in Helvetica, a replacement longer than the original can collide with
adjacent text. The title fix sidesteps this by keeping tokens short. The general
engine cannot assume that, so **preview must compute and flag overflow**
(estimated rendered width vs. original span width) and require the user to
acknowledge it before apply. Optional mitigation (note for the implementer, not
required v1): shrink font size to fit, or reflow — both add complexity; flag-and-
confirm is the minimum.

### 7.4 We are altering signed clinical records — guardrails are mandatory

The title fix is defensible precisely because it corrects *administrative
metadata to match licensure-as-of-the-session-date* — it makes the record
*accurate*, and it does so under strict controls. A general rewrite tool inside a
compliance UI inherits the obligation to keep those controls:

- **Never modify originals.** Reads from `--input`, writes to `--output`. The
  shared applier enforces this; no UI path can overwrite a source PDF. (This is
  already `fixtnpdf`'s invariant — preserve it as an engine-level guarantee.)
- **Preview → diff → explicit approve → write.** No rewrite applies without the
  user confirming a span-level diff (§5.2.3). Apply is never implicit.
- **Audit manifest on every apply** (§9): what file, what note, which spans,
  old→new text, which action, timestamp, operator. Written alongside the output
  so a rewritten record can always be reconciled against its source.
- **Post-rewrite regression check** (§5.3): the rewrite must flip the intended
  standard and regress nothing, verified against the corpus.
- **PHI stays local.** Span text and note content used for previewing/authoring
  is processed on-machine; the change-request artifact (Tier R3) is PHI-minimized
  the same way the rule artifact is, and is for local/VS Code use, not sent to an
  off-machine model without a BAA. Consistent with the Ollama-vs-Claude policy
  already in the repo.

---

## 8. Refactor steps (order of work, for the implementation phase)

1. **Create `compliance/rewrite/`**: move the applier (`apply_corrections`,
   `_normalize_text`, redact/reinsert), the `TargetSpan`/`RewritePlan` types, and
   a small action registry. No behavior change — pure extraction.
2. **Re-express the title + supervisor fixes** as `provider_title` and
   `supervisor_credential` actions registered against the new library.
3. **Reduce `fixtnpdf.py`** to a CLI that loads CSVs, registers those two
   actions, and drives the shared applier. **Regression gate:** output PDFs over
   `sourcedocs/` are identical before vs. after this step.
4. **Add the Tier-R1 declarative path**: `rules/rewrites.yaml`, generic
   locator/transform, config loading via `compliance/config.py`.
5. **Wire `trainstandards.py`**: the rewrite routes (§6), the authoring panel
   (§5), the rewritable-standard allowlist (§7.2), preview/overflow (§7.3),
   audit manifest (§9), re-evaluate loop (§5.3), and the Tier-R3 artifact route.
6. **Add `fitz` (PyMuPDF) to `requirements.txt`** for `trainstandards.py`’s span
   enumeration and as the shared applier's backend (it's already a `fixtnpdf`
   dependency; this just makes it a declared one for the web app too).

Steps 1–3 are the refactor and can land independently of any UI. Steps 4–5 are
the new authoring capability. Step 3's identical-output check is the single most
important test in the plan.

---

## 9. Audit manifest

Every apply writes a manifest next to the output PDF (e.g.
`output/<name>.rewrite.json`):

```json
{
  "source_pdf": "optum-atkins.pdf",
  "output_pdf": "optum-atkins.pdf",
  "applied_at": "2026-06-01T15:22:10Z",
  "action": "provider_title",
  "note": { "type": "progress", "service_date": "2025-10-07", "page_indices": [4,5] },
  "spans": [
    { "page_index": 4, "old_text": "Bridgid Lupetin, LPC", "new_text": "Bridgid Lupetin, LPCC", "overflow": false }
  ],
  "remediated_standard": "<id or null>",
  "operator": "<user>"
}
```

This makes any rewritten clinical record reconcilable against its source and
gives the regression loop (§5.3) a record of intent to check against.

---

## 10. Out of scope (the "later")

- True click-on-PDF span selection (needs `pdf.js`; §7.1).
- Auto-fitting/reflowing overflowing replacements (§7.3 mitigation).
- In-process hot-swap of rewrite *logic* — deliberately excluded in favor of the
  codegen-handoff artifact, consistent with `docs/rule_editing.md`.
- Any rewrite that synthesizes absent clinical content (§7.2) — permanently out
  of scope by policy, not just this phase.
- Batch rewrite across many PDFs from the UI (the CLI `fixtnpdf` path already
  covers batch; the UI authors and validates one note at a time).
```
