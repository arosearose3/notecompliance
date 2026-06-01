# Standards Trainer — User Guide

This guide explains how to use the Standards Trainer to review and improve the
way the compliance engine grades clinical notes. You do not need to know how to
code to use most of the features.

---

## Installation

You only need to do this once on a new computer.

### Step 1 — Get the code

If you received a zip file, unzip it into a folder on your computer. If the
project is in a git repository, clone it:

```
git clone <repository-url>
cd fixtnpdf
```

### Step 2 — Install Python

The tool requires **Python 3.11 or newer**. Check whether you already have it:

```
python3 --version
```

If the version shown is lower than 3.11, download the latest Python from
[python.org](https://www.python.org/downloads/) and install it.

### Step 3 — Install the Python packages

In the project folder, run:

```
pip install -r requirements.txt
```

This installs `pdfplumber` (PDF reading), `pikepdf` (PDF writing), `flask`
(the web server), and `pyyaml` (configuration files).

### Step 4 — Install Ollama (for live AI judging)

Ollama runs AI models on your own computer so no patient data ever leaves the
building. This is the recommended judge for live prompt testing.

1. Download Ollama from [ollama.com](https://ollama.com) and install it.
2. Open a terminal and pull the model used by this project:

```
ollama pull qwen3.5:9b
```

3. Ollama starts automatically in the background after installation. You can
   verify it is running with:

```
ollama list
```

You should see `qwen3.5:9b` in the list.

### Step 5 — Verify everything works

Run this quick check:

```
python trainstandards.py --input sourcedocs/ --judge ollama
```

Open your browser to **http://127.0.0.1:5000**. If you see the three-pane
layout with PDFs listed on the left, the installation is complete.

---

## What the Standards Trainer is

The Standards Trainer is a web tool that runs on your computer. It lets you:

1. **Look at any clinical note PDF** in your source folder.
2. **See how the engine graded each of the 47 documentation standards** — did the note pass, fail, or need a human to review it?
3. **Understand why** each verdict was reached — what text the engine found (or didn't find), and what question it would ask an AI reviewer.
4. **Fix things that are wrong** — add missing keywords, change how strict a standard is, or rewrite the question used to judge a standard.
5. **Track your improvements** by pinning expected grades and running a regression check to make sure your changes don't break other notes.

---

## Starting the tool

Open a terminal, go to the project folder, and run:

```
python trainstandards.py --input sourcedocs/ --judge ollama
```

Then open your browser and go to: **http://127.0.0.1:5000**

The tool will stay running until you press **Ctrl-C** in the terminal.

To start without a live AI judge (the tool still works, but "Test against
this note" won't give real answers):

```
python trainstandards.py --input sourcedocs/
```

---

## The three-pane layout

```
┌──────────────┬──────────────────────────────┬──────────────────────┐
│  PDF list    │  PDF viewer                  │  Standard cards      │
│  (left)      │  (center)                    │  (right)             │
└──────────────┴──────────────────────────────┴──────────────────────┘
```

### Left pane — PDF list

Shows every PDF in your source folder. Each entry shows the file name and how
many notes are inside it.

**Click a PDF name** to load it. The center pane will show the PDF and the
right pane will grade all its notes. This takes a few seconds — the engine is
reading the PDF and running every check in real time.

### Center pane — PDF viewer

Shows the PDF you selected. The browser's built-in PDF viewer is used, so you
can scroll, zoom, and search just like any PDF.

When you click a **"Jump to page"** button in a card's detail dialog, the
center pane jumps to that page.

### Right pane — Standard cards (accordion style)

Each note in the PDF gets its own collapsible section. Click a section header
to expand or collapse it.

When you select a PDF, the first note's section opens automatically and the
center pane jumps to that note's first page.

Each note's section shows one card for every standard (A1 through K2 — 47 total):

| Badge color | Meaning |
|---|---|
| **Red** FAIL | The rule checked for something and it was missing or wrong. |
| **Orange** REVIEW | The engine can't decide by itself — a human needs to look. |
| **Green** PASS | The rule found what it was looking for. |
| **Grey** N/A | This standard doesn't apply to this type of note. |

The section header itself shows a summary of failures and reviews so you can
spot problem notes without opening them.

---

## Looking at a card in detail

Click any non-grey card to open the **detail dialog**. The dialog has several
sections:

### Applicability and Verdict

Shows whether this standard is **Required** (R), **Conditional** (C — only
required in certain situations), or not applicable for this note type. Then
shows the verdict (Pass, Fail, Review, or N/A) and a plain-English explanation.

### Evidence

If the engine found something relevant in the note, it shows the exact text it
found. This is proof for a Pass, or clue for a Fail.

### Source pages

If the finding came from a specific page, a **Jump to page N** button lets you
go straight to it.

### Judge path

For standards that can't be checked by simple rules, the engine asks a question
— these are the "judgment" checks. The dialog shows:

- The **question** that would be sent to an AI reviewer.
- The **note text** (context) that the AI would read.
- The **answer** the AI gave (under the default "null" judge, it always says
  "manual review" because no AI is connected yet, but the question is still
  shown so you can see and improve it).

### Rule inputs — header fields

Shows all the structured data the engine extracted from the note header: date,
clinician, service code, member name, etc.

### Rule inputs — sections extracted

Shows the list of named sections the engine found in the note body (like
"diagnosis", "presenting\_problem", "medications"). If the engine missed a
section, this list is your clue.

---

## Fixing things that are wrong (the three tiers)

### Tier 1 — Add or change section synonyms

**When to use this:** A standard failed because the engine couldn't find a
named section, but the section IS there — it's just labeled differently in the
note. For example, a note might say "Reason for Referral" instead of
"Presenting Problem".

**How:**

1. Open the failing card's detail dialog.
2. Scroll down to **"Sections not found — add synonyms to fix"**. You'll see
   the section names the engine was looking for but didn't find.
3. Click **Edit synonyms** next to the missing section name.
4. You'll see a list of the current synonyms (the phrases the engine searches for).
5. Type a new phrase in the input box and click **Add**.
6. Click **Save & re-evaluate**. The tool immediately re-grades the current PDF
   with your new synonym and refreshes the cards — no restart needed.

Your change is saved to `rules/section_synonyms.yaml`. It applies to all future
evaluations.

**Also: Tier 1 — Change applicability**

If a standard is marked Required for a note type but shouldn't be, or vice
versa, click **Edit applicability matrix** in the dialog. You can change any
doc-type from Required → Conditional → Not applicable, save, and the cards
update immediately.

### Tier 2 — Edit the question used to judge a standard

**When to use this:** A standard is being judged by an AI, and the AI is
giving the wrong answer because the question isn't specific enough. You want to
rewrite the question.

**How:**

1. Open the card's detail dialog.
2. In the **Judge path** section, you'll see an **Edit judge prompt** panel.
3. The current question is shown in a text box. Edit it — you can make it more
   specific, add examples, or clarify what you're looking for.
4. Click **Test against this note** to try your new question against this note's
   text and see the AI's new verdict in real time.
   > Note: live testing requires starting the tool with `--judge ollama` (or
   > `--judge claude`). With the default null judge, the answer will always
   > be "manual review" — but you can still see and edit how the question reads.
5. If you're happy with the result, click **Save prompt**. The question is saved
   to `rules/prompts/<StandardID>.md` and will be used for all future checks.
6. If you want to go back to the original built-in question, click
   **Remove override**.

### Tier 3a — Generate a change request for Claude Code

**When to use this:** The rule needs new logic that can't be fixed by changing
synonyms or the judge question. For example, the check for late entries needs to
use a 72-hour window instead of 24 hours.

**How:**

1. Open the card's detail dialog.
2. Scroll to the bottom and click **Tier 3a: Generate change request**.
3. Choose the verdict the note should get, and describe in plain English what
   needs to change.
4. Click **Generate artifact**. The tool creates a complete document in the
   `rule_requests/` folder containing:
   - The full text of the standard.
   - The current check code.
   - The note's extracted data (no patient text).
   - Your description and desired outcome.
   - Hard rules that any code change must follow.
5. Click **Copy to clipboard** and paste it into Claude Code (or any coding AI).
   The coding AI will write the new Python code, which you then review and commit.

---

## Regression — making sure you don't break other notes

Every time you change a synonym, prompt, or rule, there's a risk it will fix
one note but break a different one. The **Regression corpus** is a safety net.

### Pinning a verdict

When a card shows the correct verdict, click **Pin verdict to corpus** in the
dialog's Actions section. This saves the expected verdict for that standard and
note. You can pin as many as you like across different PDFs.

### Running the regression check

Click the **Regression (N)** button in the top bar (N shows how many pins you
have). Then click **▶ Run**. The tool re-checks every pinned item and shows
the results:

- **Green rows** = still matching the expected verdict (good).
- **Red rows** = the verdict changed — something you did may have caused a
  regression. Investigate before applying the change to production.

The corpus is saved to `rules/corpus.json` under git, so it travels with the
code and can be run by anyone on the team.

### Reload rules

After changing any file in `rules/` directly (in a text editor or after a git
pull), click **↺ Reload rules** in the top bar. The tool picks up the new
configuration without restarting.

---

## Where files live

| Location | What it is |
|---|---|
| `rules/section_synonyms.yaml` | Section synonym overrides |
| `rules/applicability.yaml` | Applicability matrix overrides |
| `rules/thresholds.yaml` | Numeric thresholds (e.g. late-entry hours) |
| `rules/prompts/<ID>.md` | Judge question for standard ID (one file per judgment check) |
| `rules/corpus.json` | Pinned expected verdicts for regression |
| `rule_requests/` | Change-request artifacts generated by Tier 3a |
| `compliance/checks/*.py` | The actual check code (only changed via Tier 3a + code review) |

---

## Startup options

### Different PDF folder

```
python trainstandards.py --input path/to/your/pdfs/
```

### Live AI judging with Ollama (recommended — data stays on-machine)

```
python trainstandards.py --input sourcedocs/ --judge ollama
```

Ollama must be running and `qwen3.5:9b` must be installed (see Installation
above). By default the tool connects to `http://localhost:11434`.

To use a different model or a remote Ollama server:

```
python trainstandards.py --judge ollama --ollama-model mistral --ollama-url http://192.168.1.10:11434
```

### Live AI judging with Claude (sends data off-machine)

```
python trainstandards.py --input sourcedocs/ --judge claude
```

This requires the `ANTHROPIC_API_KEY` environment variable and a Business
Associate Agreement (BAA) with Anthropic before using on real patient notes.

---

## Resetting standard configurations to the original defaults

All the configuration files that the tool writes to are in the `rules/`
folder. To reset any of them, you restore or delete the file — the engine
will automatically fall back to the original built-in values.

### Reset section synonyms

The original synonyms are built into the code in
`compliance/extract/sections.py`. To go back to them, either:

- **Delete the file:** `rules/section_synonyms.yaml` → delete or rename it.
  The code defaults will be used on the next evaluation.
- **Or overwrite it with an empty config:**
  Open `rules/section_synonyms.yaml` in a text editor and replace all
  content with just `{}`. Save it.

### Reset applicability overrides

- **Delete or clear** `rules/applicability.yaml` (replace content with `{}`).
  The built-in applicability matrix in `compliance/applicability.py` will
  take effect again.

### Reset thresholds

- **Delete or clear** `rules/thresholds.yaml`.
  Default thresholds (e.g. 24-hour late-entry window) are restored.

### Reset a single judge prompt

- **Delete the file** `rules/prompts/<ID>.md` for the standard you want to
  reset. For example, to reset the D1 prompt:
  ```
  rm rules/prompts/D1.md
  ```
  The original question built into `compliance/checks/d_assessment.py` will
  be used again. You can also do this from inside the tool: open the card
  dialog → Judge path → **Remove override**.

### Reset all prompts

```
rm rules/prompts/*.md
```

Then re-run the setup step below to restore the original seeded questions:

```
git checkout rules/prompts/
```

If the project is not in git, the original prompt files are listed in the
`compliance/checks/*.py` source files — look for the `question=` argument
inside each `judge.evaluate(...)` call.

### Reset the regression corpus

The corpus is your own pinned expected verdicts — there are no built-in
entries to restore. To start fresh:

- Delete or empty the file: `rules/corpus.json` → replace with `[]`.

### Full reset (everything at once)

If your project is in git, this restores all `rules/` files to the last
committed state in one command:

```
git checkout -- rules/
```

If not in git, delete the `rules/` folder entirely and restart the tool.
The tool will recreate what it needs, and the built-in code defaults will
apply for everything else.

---

## Quick reference — what to do when a card is wrong

| Situation | Solution |
|---|---|
| Engine missed a section because it's labeled differently | Tier 1: Edit synonyms |
| A standard fires on notes where it shouldn't | Tier 1: Edit applicability matrix |
| AI judge gives wrong verdict for a judgment check | Tier 2: Edit the judge prompt |
| The detection logic itself needs to change | Tier 3a: Generate change request |
| After any change, verify nothing else broke | Run regression corpus |
