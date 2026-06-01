"""CLI entry point for trainstandards: argument parsing and server startup."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from compliance.judges.null import NullJudge
from trainui.judges import SkipJudge
from trainui.paths import RULES_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Standards-evaluation training UI")
    parser.add_argument("--input",  default="sourcedocs", help="Source PDF directory (default: sourcedocs/)")
    parser.add_argument("--output", default="output",     help="Output directory for rewritten PDFs (default: output/)")
    parser.add_argument("--port",   type=int, default=5000)
    parser.add_argument("--host",   default="127.0.0.1")
    parser.add_argument(
        "--judge", default="null", choices=["null", "ollama", "claude"],
        help="Judge for prompt testing: null (default), ollama (local), claude (API)",
    )
    parser.add_argument(
        "--ollama-model", default="qwen3.5:9b",
        help="Ollama model name (default: qwen3.5:9b)",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--no-ai", action="store_true",
        help="Skip all LLM judge calls; judgment-based checks return 'skipped' instantly",
    )
    args = parser.parse_args()

    source_dir = Path(args.input)
    if not source_dir.is_dir():
        sys.exit(f"Input directory not found: {source_dir}")

    if args.judge == "ollama":
        try:
            from compliance.judges.ollama import OllamaJudge
            inner = OllamaJudge(model=args.ollama_model, base_url=args.ollama_url)
            print(f"Using OllamaJudge — model: {args.ollama_model}  url: {args.ollama_url}")
            print("Note: all text stays on-machine (no PHI sent off-network).")
        except Exception as e:
            print(f"Cannot load OllamaJudge: {e}\nFalling back to NullJudge.", file=sys.stderr)
            inner = NullJudge()
    elif args.judge == "claude":
        try:
            from compliance.judges.claude import ClaudeJudge
            inner = ClaudeJudge()
            print("Using ClaudeJudge — PHI WARNING: note text sent to Anthropic API")
        except (ImportError, EnvironmentError) as e:
            print(f"Cannot load ClaudeJudge: {e}\nFalling back to NullJudge.", file=sys.stderr)
            inner = NullJudge()
    else:
        inner = NullJudge()

    if args.no_ai:
        inner = SkipJudge()
        print("AI judge disabled (--no-ai). Judgment-based checks will return 'skipped'.")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    from trainui.app import create_app
    app = create_app(source_dir, inner, output_dir)

    print(f"Standards Trainer — http://{args.host}:{args.port}")
    print(f"Source:  {source_dir.resolve()}")
    print(f"Output:  {output_dir.resolve()}")
    print(f"Rules:   {RULES_DIR.resolve()}")
    print(f"Judge:   {getattr(inner, 'name', args.judge)}")
    print("Press Ctrl-C to quit.\n")
    app.run(host=args.host, port=args.port, debug=False)
