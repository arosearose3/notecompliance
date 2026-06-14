# Standards Trainer — User Guide

This guide explains how to use the Standards Trainer to review and improve how
the compliance engine grades clinical notes. You do not need to know how to
code to use most of the features.

---

## Installation

You only need to do this once on a new computer. See `docs/install.md` for
detailed platform-specific steps. The short version:

1. Install Python 3.11 or newer.
2. Install Ollama and pull the model: `ollama pull qwen3.5:9b`
3. Download the project code.
4. In the project folder: `pip install -r requirements.txt`
   > This installs `pdfplumber` (reading PDFs), `pymupdf` (rewriting PDFs),
   > `flask` (the web server), and `pyyaml` (configuration files).

---

## Starting the tool

Open a terminal, go to the project folder, and run:

```
python trainstandards.py --input sourcedocs/ --judge ollama
```

Then open your browser and go to **http://127.0.0.1:5000**

The tool stays running until you press **Ctrl-C** in the terminal.

### All startup options

| Option | Default | Description |
|---|---|---|
| `--input <dir>` | `sourcedocs/` | Folder of PDF files to evaluate |
| `--output <dir>` | `output/` | Where rewritten PDFs are saved |
| `--ruleset <id>` | `optum_commercial` | Which payer's standards to evaluate against |
| `--judge <name>` | `null` | AI judge: `null`, `ollama`, or `claude` |
| `--no-ai` | off | Skip all AI calls; judgment checks show "skipped" |
| `--ollama-model <m>` | `qwen3.5:9b` | Ollama model name |
| `--ollama-url <url>` | `http://localhost:11434` | Ollama server address |
| `--port <n>` | `5000` | Port for the web UI |

**Quick recipes:**

```bash
# Fast scan — no AI, instant results
python trainstandards.py --input sourcedocs/ --no-ai

# Full AI judging (data stays on your machine)
python trainstandards.py --input sourcedocs/ --judge ollama

# Evaluate against Colorado Medicaid rules
python trainstandards.py --input sourcedocs/ --ruleset medicaid_co

# Different port if 5000 is in use
python trainstandards.py --input sourcedocs/ --port 5001
```

---

## The three-pane layout

```
┌──────────────┬──────────────────────────────┬──────────────────────┐
│  PDF list    │  PDF viewer                  │  Standard cards      │
│  (left)      │  (center)                    │  (right)             │
└──────────────┴──────────────────────────────┴──────────────────────┘
```

### Top bar

The top bar shows:

- **Standards Trainer** — the app name.
- **Ruleset selector** — a dropdown showing the active payer's rule set (e.g.
  "Optum / UBH Commercial"). The active ruleset is set at startup with
  `--ruleset`; the dropdown shows all available rulesets. To switch rulesets,
  restart the tool with the new `--ruleset` value.
- **↺ Reload rules** — picks up any changes you made to files in `rules/`
  directly (in a text editor or after a git pull) without restarting the server.
- **Regression (N)** — opens the regression panel showing your pinned expected
  verdicts. N is how many pins you have.

### Left pane — PDF list

Shows every PDF in your source folder. Each entry shows the file name and how
many notes are inside it.

**Click a PDF name** to load it. The center pane shows the PDF and the right
pane grades all its notes in real time — you'll see cards appear one by one as
each check finishes.

### Center pane — PDF viewer

Shows the PDF you selected using the browser's built-in viewer. Scroll, zoom,
and search as you would any PDF. When you click a **"Jump to page"** button in
a card's detail dialog, the center pane jumps to that page.

### Right pane — Standard cards (accordion style)

Each note in the PDF gets its own collapsible section. Click a section header
to expand or collapse it. When you select a PDF, the first note opens
automatically.

Each note shows one card for every standard in the active ruleset:

| Badge | Meaning |
|---|---|
| 🔴 **FAIL** | The rule checked and found something missing or wrong. |
| 🟠 **REVIEW** | The engine can't decide — a human needs to look. |
| 🟢 **PASS** | The rule found what it was looking for. |
| ⬜ **N/A** | This standard doesn't apply to this note type. |
| ➖ **SKIPPED** | AI judging was disabled (`--no-ai`). Re-run with `--judge ollama` to evaluate. |

The section header shows a summary count of failures and reviews so you can
spot problem notes without opening them.

---

## Looking at a card in detail

Click any non-grey, non-skipped card to open the **detail dialog**.

### Applicability and Verdict

Shows whether this standard is **Required** (R) or **Conditional** (C) for
this note type, and the verdict with a plain-English explanation.

### Payer standard (verbatim)

The exact wording from the payer's documentation requirements — what the rule
is actually checking for.

### Evidence

The exact text from the note that the engine found. This is the proof for a
Pass, or a clue for a Fail.

### Source pages

**Jump to page N** buttons go straight to the relevant page in the center pane.

### Judge path

For standards that need AI judgment, shows the question sent to the AI, the
note text (context) the AI read, and the AI's answer. Under `--no-ai` or the
default null judge, the question is still shown so you can read and improve it
without spending AI time.

### Rule inputs

Shows the structured data extracted from the note: header fields (date,
clinician, service code) and the list of named sections found in the note body
(diagnosis, presenting\_problem, medications, etc.). If the engine missed a
section, this list tells you what it did and didn't find.

### Actions

At the bottom of every dialog:

- **📌 Pin verdict to corpus** — saves the current verdict as the expected
  value for regression testing (see Regression below).
- **Tier 3a: Generate change request** — creates a handoff document for making
  a code-level rule change.
- **Author a rewrite…** — appears on failing cards for standards that can be
  corrected by editing the PDF (see PDF Rewrite below). Not shown for standards
  whose remedy requires new clinical content — those can't be fixed by editing
  the file.

---

## Rulesets — evaluating against different payers

Different insurance payers have different documentation requirements. The
Standards Trainer supports multiple **rulesets** — one per payer — so you can
evaluate the same notes against Commercial or Medicaid rules and see where the
verdicts differ.

### Selecting a ruleset

```bash
python trainstandards.py --input sourcedocs/ --ruleset optum_commercial  # default
python trainstandards.py --input sourcedocs/ --ruleset medicaid_co
```

The active ruleset appears in the top bar dropdown and is shown in the startup
banner:

```
Ruleset: Colorado Medicaid / HCPF (medicaid_co)
```

### Available rulesets

| ID | Label | Description |
|---|---|---|
| `optum_commercial` | Optum / UBH Commercial | Default. Optum Provider Manual content standards. |
| `medicaid_co` | Colorado Medicaid / HCPF | Colorado Medicaid behavioral health standards (inherits Commercial as baseline; overrides where Medicaid differs). |

### Where ruleset data lives

Each ruleset has its own subtree under `rules/`:

```
rules/
  section_synonyms.yaml          ← shared across all rulesets (EHR vocabulary)
  optum_commercial/
    ruleset.yaml                 ← standard list, order, titles
    applicability.yaml           ← R/C/None per doc type
    thresholds.yaml              ← numeric limits (e.g. late-entry hours)
    payer_text.yaml              ← verbatim payer requirement text
    prompts/<ID>.md              ← judge question overrides
    corpus.json                  ← pinned verdicts (per-ruleset)
    rewrites.yaml                ← Tier-R1 declarative PDF rewrites
  medicaid_co/
    ruleset.yaml
    applicability.yaml
    thresholds.yaml
    ...
```

All of the editable files listed in the **Fixing things** section below
(synonyms, applicability, thresholds, prompts, corpus) are **per-ruleset**
when you use `--ruleset`. Pinning a verdict pins it under the active ruleset's
corpus; running regression checks that ruleset's corpus.

---

## Fixing things that are wrong (the three tiers)

### Tier 1 — Section synonyms and applicability

**When to use:** A standard failed because the engine couldn't find a named
section, but the section is there — labeled differently. For example, a note
might say "Reason for Referral" instead of "Presenting Problem."

**Add a synonym:**

1. Open the failing card's detail dialog.
2. Scroll to **"Sections not found — add synonyms to fix"**.
3. Click **Edit synonyms** next to the missing section name.
4. Type the new phrase and click **Add**, then **Save & re-evaluate**.

The tool immediately re-grades the PDF with your new synonym. Your change is
saved to `rules/section_synonyms.yaml` (shared across all rulesets — section
names are EHR vocabulary, not payer policy).

**Change applicability (R / C / N/A):**

Click **Edit applicability matrix** in the dialog to change whether a standard
is Required, Conditional, or not applicable for a given note type. Changes are
saved to `rules/<ruleset>/applicability.yaml` and take effect immediately. They
only affect the active ruleset.

**Change a threshold:**

Thresholds (e.g. the number of hours after which a late-entry notation is
required) live in `rules/<ruleset>/thresholds.yaml`. Edit the file directly
and click **↺ Reload rules** in the top bar.

### Tier 2 — Edit the judge question

**When to use:** A standard is graded by AI and the AI is giving the wrong
answer because the question isn't specific enough.

1. Open the card's detail dialog → **Judge path** section.
2. Edit the question in the text box.
3. Click **Test against this note** to try it with the live AI judge.
   > Requires `--judge ollama` or `--judge claude`. With null judge or
   > `--no-ai`, the question is still editable but test results are placeholder.
4. Click **Save prompt** to save to `rules/<ruleset>/prompts/<ID>.md`.
5. Click **Remove override** to go back to the built-in question.

### Tier 3a — Generate a code change request

**When to use:** The detection logic itself needs to change — not just
synonyms, applicability, or the AI question. For example, adding a new pattern
the check should recognize, or changing the window for a time-based rule.

1. Open the card's detail dialog → scroll to the bottom.
2. Click **Tier 3a: Generate change request**.
3. Describe what needs to change and click **Generate artifact**.
4. The tool creates a document in `rule_requests/` with the full standard text,
   the current check code, the note's extracted data (no patient text), your
   description, and hard constraints the new code must satisfy.
5. Click **Copy to clipboard** and paste it into Claude Code. The AI writes
   the new code; you review and commit it.

---

## PDF Rewrite — correcting administrative metadata

Some failing standards can be fixed by **editing the PDF itself** — correcting
a credential, adding a boilerplate phrase, normalizing a field that exists but
is labeled wrong. The Standards Trainer can do this under your supervision.

**What can be rewritten:**

| Standard | What's fixable |
|---|---|
| A1 | Member ID / name metadata |
| A2–A3 | Admin header fields |
| B1–B2 | Date and entry timestamp fields |
| F6–F7 | Clinician credential and signature |
| K1 | Telehealth delivery statement |

Standards whose remedy is **absent clinical content** (a missing Mental Status
Exam, an unwritten risk assessment, etc.) do not show a rewrite button. Those
require new documentation, not a file edit.

### How to author a rewrite

1. Open a failing card for a rewritable standard.
2. Click **Author a rewrite…** in the Actions section.
3. A panel opens with four steps:

   **Step 1 — Select spans.** The tool lists every text span in the note
   (header spans highlighted first — those are the usual targets). Tick the
   span(s) you want to fix.

   **Step 2 — Choose action.** Pick the type of correction from the dropdown
   (e.g. "Correct provider credential"). Built-in actions appear automatically.

   **Step 3 — Preview.** Click **Preview changes**. The tool shows a
   side-by-side diff of every span it will change. If any replacement is wider
   than the original, it warns you — tick the acknowledgement to proceed.

   **Step 4 — Apply.** Click **Apply rewrite to PDF**. The corrected PDF is
   written to the output folder (`output/` by default). The original is never
   touched.

4. A link appears to **View rewritten PDF** — the center pane can show the
   corrected copy. You can then **Re-evaluate** to confirm the card flips from
   Fail to Pass.

> **Note:** All rewritten PDFs go to the `--output` directory. An audit trail
> (`.rewrite.json`) is written alongside every corrected PDF recording exactly
> what changed, when, and which standard it addressed.

### Tier R1 — Declarative rewrites (no code)

Simple find-and-replace rewrites (e.g. "add a telehealth statement to every
signature block") can be authored entirely in the UI and saved to
`rules/<ruleset>/rewrites.yaml` without writing Python. These are available in
the action dropdown once saved.

### Tier R3 — Data-driven rewrites (codegen)

Rewrites that need date-math or CSV lookup (like the credential fix that checks
licensure dates) require a code change. Click **Tier 3: Generate codegen
request** to create an artifact you can paste into Claude Code — same
workflow as Tier 3a for rule changes.

---

## Regression — making sure you don't break other notes

Every time you change a synonym, prompt, threshold, or rule, there's a risk it
fixes one note but breaks another. The **regression corpus** is the safety net.

### Pinning a verdict

When a card shows the correct verdict, click **📌 Pin verdict to corpus** in
the dialog. This saves the expected verdict for that standard, note, and PDF.
Pins are stored in `rules/<ruleset>/corpus.json` — they travel with the code.

### Running the regression check

Click **Regression (N)** in the top bar → **▶ Run**. The tool re-checks every
pinned item against the active ruleset and shows results:

- **Green rows** — verdict still matches the expected value. ✓
- **Red rows** — verdict changed. Something may have regressed. Investigate
  before shipping the change.

The corpus only contains entries for the active ruleset, so Commercial and
Medicaid pins don't interfere with each other.

### Reload rules

After editing any file in `rules/` directly or after a `git pull`, click
**↺ Reload rules** in the top bar. Config changes take effect immediately
without restarting.

---

## Where files live

### Shared (not ruleset-specific)

| Location | What it is |
|---|---|
| `rules/section_synonyms.yaml` | Section synonym overrides (EHR vocabulary, shared across payers) |
| `rule_requests/` | Change-request artifacts generated by Tier 3a and Tier R3 |
| `output/` | Rewritten PDFs and their `.rewrite.json` audit manifests |
| `compliance/checks/*.py` | Check code — only changed via Tier 3a + code review |

### Per-ruleset (under `rules/<ruleset_id>/`)

| File | What it is |
|---|---|
| `ruleset.yaml` | Standard list, order, and titles |
| `applicability.yaml` | R / C / None per doc type (overrides the built-in matrix) |
| `thresholds.yaml` | Numeric limits (e.g. `late_entry_hours: 24`) |
| `payer_text.yaml` | Verbatim requirement text shown in card dialogs |
| `prompts/<ID>.md` | Judge question override for a specific standard |
| `corpus.json` | Pinned expected verdicts for regression |
| `rewrites.yaml` | Tier-R1 declarative PDF rewrite actions |

---

## Resetting configurations to defaults

All editable config lives in `rules/<ruleset>/`. To reset anything, restore or
delete the file — the engine falls back to built-in values.

### Reset section synonyms (shared)

Delete or clear `rules/section_synonyms.yaml` (replace content with `{}`).
Built-in synonyms in `compliance/extract/sections.py` take effect.

### Reset applicability for a ruleset

Delete or clear `rules/<ruleset>/applicability.yaml` (replace with `{}`).

### Reset thresholds for a ruleset

Delete or clear `rules/<ruleset>/thresholds.yaml`.

### Reset a single judge prompt

Delete `rules/<ruleset>/prompts/<ID>.md`, or use the **Remove override** button
in the card dialog.

### Reset all prompts for a ruleset

```bash
rm rules/optum_commercial/prompts/*.md
git checkout -- rules/optum_commercial/prompts/   # if using git
```

### Reset the regression corpus

Replace `rules/<ruleset>/corpus.json` with `[]`.

### Full reset (everything, all rulesets)

```bash
git checkout -- rules/   # restores all rules/ files to last commit
```

If not using git, delete `rules/<ruleset>/` subdirectories (keep
`section_synonyms.yaml` at the top level) and restart the tool.

---

## Quick reference — what to do when a card is wrong

| Situation | Solution |
|---|---|
| Engine missed a section because it's labeled differently | Tier 1: Edit synonyms |
| A standard fires on notes where it shouldn't (or vice versa) | Tier 1: Edit applicability matrix |
| Threshold is wrong (e.g. late-entry window) | Edit `rules/<ruleset>/thresholds.yaml`, reload |
| AI judge gives wrong verdict | Tier 2: Edit the judge prompt |
| Detection logic itself needs to change | Tier 3a: Generate change request |
| Admin metadata in PDF is wrong (credential, date field) | PDF Rewrite: Author a rewrite |
| After any change, verify nothing else broke | Run regression corpus |
| Want to evaluate against a different payer | Restart with `--ruleset <id>` |
