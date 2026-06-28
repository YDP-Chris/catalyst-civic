#!/usr/bin/env python
"""
Persists Insight objects into m1_insights.insights.

Upsert on dedupe_key: a re-run of the same lens over the same data refreshes
the existing row (summary, metrics, evidence, updated_at) instead of creating
duplicates, while preserving first_seen_at. This keeps the insights table a
stable, deduplicated index rather than an append-only log.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.db import cursor  # noqa: E402
from common.logger import log  # noqa: E402
from insight_engine.models import ENGINE_VERSION, Insight  # noqa: E402

UPSERT_SQL = """
INSERT INTO m1_insights.insights
    (insight_id, dedupe_key, lens, title, summary, severity, confidence,
     entity_refs, metrics, evidence, source_lane, engine_version)
VALUES
    (%(insight_id)s, %(dedupe_key)s, %(lens)s, %(title)s, %(summary)s,
     %(severity)s, %(confidence)s, %(entity_refs)s, %(metrics)s, %(evidence)s,
     %(source_lane)s, %(engine_version)s)
ON CONFLICT (dedupe_key) DO UPDATE SET
    title       = EXCLUDED.title,
    summary     = EXCLUDED.summary,
    severity    = EXCLUDED.severity,
    confidence  = EXCLUDED.confidence,
    entity_refs = EXCLUDED.entity_refs,
    metrics     = EXCLUDED.metrics,
    evidence    = EXCLUDED.evidence,
    engine_version = EXCLUDED.engine_version,
    updated_at  = now();
"""


def _params(insight: Insight) -> dict:
    return {
        "insight_id": insight.insight_id(),
        "dedupe_key": insight.dedupe_key(),
        "lens": insight.lens,
        "title": insight.title,
        "summary": insight.summary,
        "severity": insight.severity,
        "confidence": insight.confidence,
        "entity_refs": json.dumps(insight.entity_refs),
        "metrics": json.dumps(insight.metrics),
        "evidence": json.dumps(insight.evidence_json()),
        "source_lane": insight.source_lane,
        "engine_version": ENGINE_VERSION,
    }


def write_insights(insights: list[Insight]) -> int:
    if not insights:
        log("No insights to write.")
        return 0
    with cursor() as cur:
        for insight in insights:
            cur.execute(UPSERT_SQL, _params(insight))
    log(f"Upserted {len(insights)} insight(s) into m1_insights.insights.")
    return len(insights)


def preview_insights(insights: list[Insight]) -> None:
    """Dry-run output: print what would be written, no DB writes."""
    for ins in insights:
        log(
            f"[{ins.severity.upper()}] ({ins.lens}) {ins.title} "
            f"| confidence={ins.confidence:.2f} | evidence={len(ins.evidence)} "
            f"| id={ins.insight_id()}"
        )
