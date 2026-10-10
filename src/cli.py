"""CLI entry point for the Secretary Agent.

Usage:
    # Demo mode (with sample data)
    python -m src.cli --demo

    # Process exceptions from a JSON file
    python -m src.cli --goal "Close out September" --exceptions examples/sample_exceptions.json

    # Process both documents and exceptions
    python -m src.cli --goal "Reconcile October" --documents docs.json --exceptions exceptions.json

    # Output as JSON
    python -m src.cli --demo --json

    # Interactive mode
    python -m src.cli --interactive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import DocumentInfo, ExceptionEvent
from .secretary import Secretary


def load_json_file(path: str) -> list[dict]:
    """Load a JSON file and return a list of dicts."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    return data


def parse_exceptions(data: list[dict]) -> list[ExceptionEvent]:
    """Parse raw dict data into ExceptionEvent objects."""
    return [ExceptionEvent(**item) for item in data]


def parse_documents(data: list[dict]) -> list[DocumentInfo]:
    """Parse raw dict data into DocumentInfo objects."""
    return [DocumentInfo(**item) for item in data]


def main():
    parser = argparse.ArgumentParser(
        description="Secretary Agent — Task Coordinator for Document Processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli --demo
  python -m src.cli --goal "Close out September" --exceptions examples/sample_exceptions.json
  python -m src.cli --goal "Reconcile October" --exceptions exceptions.json --json
  python -m src.cli --interactive
        """,
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with sample data (no file input needed)",
    )
    parser.add_argument(
        "--goal",
        type=str,
        default="Close out September",
        help="The business goal for this run",
    )
    parser.add_argument(
        "--exceptions",
        type=str,
        default=None,
        help="Path to JSON file with exception events from Financial agent",
    )
    parser.add_argument(
        "--documents",
        type=str,
        default=None,
        help="Path to JSON file with document info from Logistics agent",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve chase emails (TESTING ONLY — never use in production)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode — prompt for goal and inputs",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write output to a file instead of stdout",
    )

    args = parser.parse_args()

    secretary = Secretary()

    # ------------------------------------------------------------------
    # Interactive mode
    # ------------------------------------------------------------------
    if args.interactive:
        print("=" * 60)
        print("  Secretary Agent — Interactive Mode")
        print("=" * 60)
        print()

        goal = input("Enter your goal (e.g. 'Close out September'): ").strip()
        if not goal:
            goal = "Close out September"

        exceptions_path = input(
            "Path to exceptions JSON file (or press Enter for demo data): "
        ).strip()

        print()
        print("Processing...")
        print()

        if exceptions_path:
            raw = load_json_file(exceptions_path)
            exceptions = parse_exceptions(raw)
        else:
            print("(No exceptions file provided — using sample data)")
            exceptions = secretary._sample_exceptions()

        result = secretary.run(
            goal=goal,
            exceptions=exceptions,
            auto_approve_emails=args.auto_approve,
        )

        output = secretary.format_result(result)
        print(output)
        return

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------
    if args.demo:
        print("Running in DEMO mode with sample data...\n")

        result = secretary.run(
            goal=args.goal,
            exceptions=secretary._sample_exceptions(),
            documents=secretary._sample_documents(),
            auto_approve_emails=args.auto_approve,
        )

        if args.json:
            output = secretary.result_to_json(result)
        else:
            output = secretary.format_result(result)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"Output written to {args.output}")
        else:
            print(output)
        return

    # ------------------------------------------------------------------
    # File-based mode
    # ------------------------------------------------------------------
    exceptions: list[ExceptionEvent] = []
    documents: list[DocumentInfo] = []

    if args.exceptions:
        raw_exceptions = load_json_file(args.exceptions)
        exceptions = parse_exceptions(raw_exceptions)

    if args.documents:
        raw_docs = load_json_file(args.documents)
        documents = parse_documents(raw_docs)

    # If neither is provided, fall back to demo data
    if not exceptions and not documents:
        print("No input files provided. Running in demo mode...\n")
        exceptions = secretary._sample_exceptions()
        documents = secretary._sample_documents()

    result = secretary.run(
        goal=args.goal,
        exceptions=exceptions,
        documents=documents,
        auto_approve_emails=args.auto_approve,
    )

    if args.json:
        output = secretary.result_to_json(result)
    else:
        output = secretary.format_result(result)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
