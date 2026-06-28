#!/usr/bin/env python
"""
Insight Engine — entry point.

Runs the registered lenses read-only against the Catalyst Civic database,
collects evidence-backed Insight objects, and upserts them into
m1_insights.insights. Each run writes a manifest line for traceability,
matching the manifest-driven lifecycle used by the rest of the platform.

Usage:
  python run_insight_engine.py                 # all lenses, write to DB
  python run_insight_engine.py --dry-run       # analyze + print, no DB write
  python run_insight_engine.py --lens influence,spending
  python run_insight_engine.py --init-schema   # create m1_insights schema first
  python run_insight_engine.py --list-lenses

Reads PG_* env vars for the database connection (same as the push scripts).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Make `common` and `insight_engine` importable from the module's src/ dir.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from common.db import connect  # noqa: E402
from common.logger import log  # noqa: E402
from insight_engine.models import ENGINE_VERSION  # noqa: E402
from insight_engine.registry import get_lenses, lens_names  # noqa: E402
from insight_engine.schema import init_schema  # noqa: E402
from insight_engine.writer import preview_insights, write_insights  # noqa: E402

MANIFEST_FILE = Path(__file__).resolve().parents[1] / "logs" / "INSIGHT_RUN_MANIFEST.jsonl"


def _write_manifest(record: dict) -> None:
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def run(lens_filter: list[str] | None, dry_run: bool) -> int:
    lenses = get_lenses(lens_filter)
    if not lenses:
        log(f"No matching lenses. Available: {', '.join(lens_names())}", level="ERROR")
        return 1

    run_id = f"INSIGHT_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
    log(f"Starting {run_id} | engine={ENGINE_VERSION} | lenses={[l.name for l in lenses]}")

    all_insights = []
    per_lens_counts: dict[str, int] = {}
    errors: dict[str, str] = {}

    # Read-only connection shared across lenses; never committed (no writes here).
    conn = connect()
    conn.set_session(readonly=True)
    try:
        import psycopg2.extras

        for lens in lenses:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                found = lens.analyze(cur)
                per_lens_counts[lens.name] = len(found)
                all_insights.extend(found)
                log(f"  {lens.name}: {len(found)} insight(s)")
            except Exception as exc:  # one bad lens must not sink the run
                errors[lens.name] = str(exc)
                log(f"  {lens.name}: FAILED — {exc}", level="ERROR")
            finally:
                cur.close()
    finally:
        conn.close()

    if dry_run:
        log("DRY RUN — no database writes. Preview:")
        preview_insights(all_insights)
        written = 0
    else:
        written = write_insights(all_insights)

    record = {
        "run_id": run_id,
        "engine_version": ENGINE_VERSION,
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "lenses": [l.name for l in lenses],
        "per_lens_counts": per_lens_counts,
        "total_insights": len(all_insights),
        "written": written,
        "errors": errors,
    }
    _write_manifest(record)
    log(f"{run_id} complete | total={len(all_insights)} written={written} errors={len(errors)}")
    return 0 if not errors else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalyst Civic Insight Engine")
    parser.add_argument("--lens", help="Comma-separated lens names to run (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and print; do not write to DB")
    parser.add_argument("--init-schema", action="store_true", help="Create m1_insights schema, then run")
    parser.add_argument("--list-lenses", action="store_true", help="List available lenses and exit")
    args = parser.parse_args()

    if args.list_lenses:
        for name in lens_names():
            print(name)
        return 0

    if args.init_schema:
        init_schema()

    lens_filter = args.lens.split(",") if args.lens else None
    return run(lens_filter, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
