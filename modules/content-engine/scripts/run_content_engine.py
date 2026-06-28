#!/usr/bin/env python
"""
Content Engine — entry point.

Reads insights from m1_insights.insights and writes a markdown report into
m1_insights.reports via Claude.

Usage:
  python run_content_engine.py                       # report from all lenses
  python run_content_engine.py --lens influence      # one lens
  python run_content_engine.py --severity high       # high-severity only
  python run_content_engine.py --dry-run             # print, do not write
  python run_content_engine.py --audience legal      # tag the report's audience

Requires ANTHROPIC_API_KEY and the PG_* env vars.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from content_engine.reporter import generate_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalyst Civic Content Engine")
    parser.add_argument("--lens", help="Limit to one lens (influence|spending|topics|votes)")
    parser.add_argument("--limit", type=int, default=40, help="Max insights to include")
    parser.add_argument(
        "--severity",
        choices=["high", "notable", "all"],
        default="notable",
        help="Minimum severity to include (default: notable)",
    )
    parser.add_argument("--audience", default="general", help="Audience tag (general|legal|press)")
    parser.add_argument("--dry-run", action="store_true", help="Print the report; do not write to DB")
    args = parser.parse_args()

    min_sev = None if args.severity == "all" else args.severity
    result = generate_report(
        lens=args.lens,
        limit=args.limit,
        min_severity=min_sev,
        audience=args.audience,
        dry_run=args.dry_run,
    )

    status = result.get("status")
    if status == "no_insights":
        print("No insights matched. Run the insight engine first.")
        return 1
    if status == "dry_run":
        print(f"# DRY RUN — {result['count']} insight(s)\n")
        print(result["body_md"])
        return 0
    print(f"Wrote report {result['report_id']} ('{result['title']}') "
          f"from {result['insight_count']} insight(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
