# trainstandards.py — Design Document

## Purpose

`trainstandards.py` is an interactive standards-evaluation training UI. It lets
a clinician, supervisor, or developer load any PDF from the source directory,
see how the compliance engine grades each of the 47 standards (A1–K2), and
drill into *why* each verdict was reached — including the exact question that
would be sent to an LLM judge. This inspection loop is the precondition for
tuning rules and judge prompts against real notes.

## Usage

```
python trainstandards.py [--input sourcedocs/] [--port 5000] [--host 127.0.0.1] [--judge null|claude]
```

`--input` defaults to `sourcedocs/` (same convention as `scanner.py`).  
`--judge claude` wires in `ClaudeJudge` (requires `ANTHROPIC_API_KEY` and a BAA).

Open `http://127.0.0.1:5000` in a browser after starting the server.

## Layout

```
┌────────────┬───────────────────────────┬─────────────────────────┐
│ PDF list   │   PDF viewer (iframe)      │  Standard result cards  │
│ (sidebar)  │   native browser PDF       │  grouped per note;      │
│ click →    │   #page=N jump support     │  all 47, greyed if N/A  │
│ load doc   │                            │  click card → dialog    │
└────────────┴───────────────────────────┴─────────────────────────┘
                                          modal dialog: determination process
```

- **Left** — PDF list with note counts, populated from `--input` directory.
- **Center** — Native browser PDF iframe; jumps to `#page=N` when the user
  clicks a note-group header or a "Jump to page" button in the dialog.
- **Right** — Accordion list of notes. Each accordion item header shows the
  note type, member, date, and a quick fail/review count badge. Click a header
  to expand that note's 47 standard cards and collapse any currently open note.
  Clicking a PDF in the left pane auto-opens the first note's accordion and
  scrolls the pane to the top. Cards are color-coded: red = fail, orange =
  manual review, green = pass, grey = not applicable. The pane header shows
  total failure and review counts across all notes in the file.

## Determination dialog

Clicking any non-greyed card opens a modal showing:

1. **Applicability** — Required (R) or Conditional (C) for this note type.
2. **Verdict** — colored badge + full rationale text.
3. **Evidence** — excerpts from the note that triggered the verdict.
4. **Source pages** — "Jump to page N" buttons that move the center PDF viewer.
5. **Judge path** — for judgment-required checks (D1, D8, E5, F5, etc.), the
   exact `question` sent to the judge, the `context` excerpt, and the judge's
   verdict/rationale. Under `NullJudge` this surfaces the question that *would*
   go to Claude — useful for prompt design without an LLM dependency.
6. **Rule inputs** — the header fields extracted from the note (date, clinician,
   service code, etc.) and the list of named sections the rule engine found.

## Architecture

Single-file Flask application with vanilla-JS frontend embedded as a string
(no build step, no external JS dependencies).

### Flask routes

| Route | Purpose |
|---|---|
| `GET /` | Serves the single-page HTML/CSS/JS |
| `GET /api/pdfs` | JSON list of `*.pdf` files + note counts |
| `GET /pdf/<name>` | Raw PDF bytes (path-restricted to `--input` dir) |
| `GET /api/evaluate?pdf=<name>` | Run live compliance checks; return JSON |

### RecordingJudge

A thin wrapper satisfying the `compliance/judges/base.py` `Judge` protocol.
It delegates every `evaluate(question, context)` call to an inner judge
(`NullJudge` or `ClaudeJudge`) and records the call — question, context
snippet, verdict, rationale — so the dialog can display the full judge trace
without modifying any of the 47 check classes.

### Per-check evaluation loop

For each note in the clicked PDF, the app iterates `ALL_CHECKS` (same registry
as `compliance/runner.py`) and wraps each check's call in its own fresh
`RecordingJudge`, so recorded calls map unambiguously to one standard. It then
builds a card for every entry in `STANDARD_TITLES` — evaluated standards get
real `CheckResult` data; matrix-excluded standards get a synthetic greyed card.

### Compliance package — consumed as-is

No changes to the `compliance/` package. The app imports:

- `compliance.ingest.split_notes()` — extract notes from a PDF
- `compliance.runner.ALL_CHECKS` — the check registry
- `compliance.applicability.applies()` / `get_applicable_standards()` — matrix
- `compliance.models.ContextBundle` — for cross-note checks (e.g. F5)
- `compliance.judges.null.NullJudge` / `compliance.judges.claude.ClaudeJudge`

### Page number conventions

`Note.page_indices` and `Page.index` are **0-based** within the source PDF.
The browser PDF hash (`#page=N`) is **1-based**. The app converts on the
server side: all `page_numbers` values in the JSON are already 1-based.

## Dependencies

`flask` — added to `requirements.txt`. Everything else (`pdfplumber`,
`pikepdf`) was already present. PDF rendering is handled by the browser natively.

## Out of scope (planned for later)

- Capturing and persisting human corrections to findings
- Editing rules or judge prompts in the UI
- In-PDF excerpt highlighting (would require pdf.js)
- Structured per-step rule traces (would require instrumenting the 47 checks)
- Aggregate/longitudinal views across multiple audit runs
