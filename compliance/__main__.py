"""
python -m compliance audit --input <dir> --output <dir> [--judge null|claude]

Subcommands:
  audit    Run compliance checks against a directory of PDFs
  scan     Quick diagnostic: list notes and doc types (no checks)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_audit(args: argparse.Namespace) -> None:
    from compliance.runner import run_batch
    from compliance.report.json_writer import write_jsonl
    from compliance.report.csv_writer import write_csv
    from compliance.report.html_writer import write_html

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Select judge
    judge = None
    if args.judge == "claude":
        try:
            from compliance.judges.claude import ClaudeJudge
            judge = ClaudeJudge()
            print("Using ClaudeJudge (PHI WARNING: note text sent to Anthropic API)")
        except (ImportError, EnvironmentError) as e:
            print(f"Cannot load ClaudeJudge: {e}\nFalling back to NullJudge.", file=sys.stderr)
    # else NullJudge (default)

    print(f"Auditing PDFs in {input_dir} ...")
    reports = run_batch(input_dir, judge=judge)

    if not reports:
        print("No notes found.")
        return

    # Summary to console
    total_fail = sum(len(r.failures) for r in reports)
    total_mr   = sum(len(r.manual_reviews) for r in reports)
    print(f"\n{len(reports)} note(s) audited.")
    print(f"  {total_fail} failure(s)   {total_mr} manual-review item(s)")

    # Write outputs
    jsonl_path = output_dir / "findings.jsonl"
    csv_path   = output_dir / "findings.csv"
    html_dir   = output_dir / "html"

    write_jsonl(reports, jsonl_path)
    write_csv(reports, csv_path, only_failures=not args.all)
    write_html(reports, html_dir)

    print(f"\nOutputs written to {output_dir}/")
    print(f"  {jsonl_path.name}  (all findings, newline-delimited JSON)")
    print(f"  {csv_path.name}    (fail + manual_review rows)")
    print(f"  html/index.html    (per-note HTML reports)")


def cmd_scan(args: argparse.Namespace) -> None:
    from compliance.ingest import ingest_directory
    input_dir = Path(args.input)
    notes = ingest_directory(input_dir)
    if not notes:
        print(f"No notes found in {input_dir}")
        return
    print(f"{'File':<40}  {'Type':<16}  {'Member':<28}  {'Date':<12}  {'Clinician'}")
    print("-" * 120)
    for note in notes:
        h = note.header
        print(
            f"{note.source_pdf.name:<40}  "
            f"{note.note_type:<16}  "
            f"{(h.member_name or '?'):<28}  "
            f"{str(h.service_date or '?'):<12}  "
            f"{h.clinician or '?'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m compliance",
        description="Clinical record compliance audit engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # audit
    audit_p = sub.add_parser("audit", help="Run compliance checks")
    audit_p.add_argument("--input",  required=True, help="Directory of input PDFs")
    audit_p.add_argument("--output", required=True, help="Output directory for reports")
    audit_p.add_argument("--judge",  default="null", choices=["null", "claude"],
                         help="Judge to use (default: null — no LLM)")
    audit_p.add_argument("--all", action="store_true",
                         help="Include pass/N/A rows in CSV output")

    # scan
    scan_p = sub.add_parser("scan", help="List notes without running checks")
    scan_p.add_argument("--input", required=True, help="Directory of input PDFs")

    args = parser.parse_args()
    if args.command == "audit":
        cmd_audit(args)
    elif args.command == "scan":
        cmd_scan(args)


if __name__ == "__main__":
    main()
