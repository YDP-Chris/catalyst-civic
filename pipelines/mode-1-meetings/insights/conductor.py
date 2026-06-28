#!/usr/bin/env python
"""
Insights pipeline conductor.

Runs the two-stage flow end to end:
  1. Insight Engine  — read the civic DB, write evidence-backed insights
  2. Content Engine  — read insights, write a report back to Postgres

Mirrors the conductor pattern used by the agenda pipeline: a thin orchestrator
that shells the stage scripts in order, with a per-run log line. Each stage is
independently runnable; this just chains them for a scheduled / one-shot run.

Usage:
  python conductor.py                 # full run: insights + report
  python conductor.py --insights-only
  python conductor.py --report-only
  python conductor.py --init-schema   # create m1_insights schema first
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INSIGHT_RUNNER = REPO_ROOT / "modules" / "insight-engine" / "scripts" / "run_insight_engine.py"
CONTENT_RUNNER = REPO_ROOT / "modules" / "content-engine" / "scripts" / "run_content_engine.py"
PYTHON = sys.executable


def _log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [CONDUCTOR] {msg}", flush=True)


def _run(script: Path, extra_args: list[str]) -> int:
    cmd = [PYTHON, str(script), *extra_args]
    _log(f"running {script.name} {' '.join(extra_args)}")
    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalyst Civic Insights pipeline")
    parser.add_argument("--insights-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--init-schema", action="store_true", help="Create m1_insights schema first")
    parser.add_argument("--lens", help="Restrict both stages to one lens")
    args = parser.parse_args()

    lens_args = ["--lens", args.lens] if args.lens else []

    if not args.report_only:
        insight_args = list(lens_args)
        if args.init_schema:
            insight_args.append("--init-schema")
        code = _run(INSIGHT_RUNNER, insight_args)
        if code not in (0, 2):  # 2 = some lenses errored but run completed
            _log(f"insight engine failed (exit {code}); stopping.")
            return code

    if not args.insights_only:
        code = _run(CONTENT_RUNNER, lens_args)
        if code != 0:
            _log(f"content engine exited {code}.")
            return code

    _log("pipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
