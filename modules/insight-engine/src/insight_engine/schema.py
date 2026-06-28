#!/usr/bin/env python
"""
Idempotent schema initializer for the `m1_insights` Postgres schema.

Follows the repo convention of building schema in Python (see the agenda
schema_sculptor / migrator) rather than committing raw .sql. Safe to run
repeatedly: every statement is IF NOT EXISTS.

Two tables:
  m1_insights.insights  — atomic, evidence-backed findings from the lenses
  m1_insights.reports   — long-form reports written by the content engine
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # add src/ to path

from common.db import cursor  # noqa: E402
from common.logger import log  # noqa: E402

DDL = [
    "CREATE SCHEMA IF NOT EXISTS m1_insights;",
    """
    CREATE TABLE IF NOT EXISTS m1_insights.insights (
        insight_id      TEXT PRIMARY KEY,
        dedupe_key      TEXT UNIQUE NOT NULL,
        lens            TEXT NOT NULL,
        title           TEXT NOT NULL,
        summary         TEXT NOT NULL,
        severity        TEXT NOT NULL DEFAULT 'notable',
        confidence      NUMERIC NOT NULL DEFAULT 0.5,
        entity_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
        metrics         JSONB NOT NULL DEFAULT '{}'::jsonb,
        evidence        JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_lane     TEXT NOT NULL DEFAULT 'insight_engine',
        engine_version  TEXT NOT NULL,
        first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_insights_lens ON m1_insights.insights (lens);",
    "CREATE INDEX IF NOT EXISTS idx_insights_severity ON m1_insights.insights (severity);",
    "CREATE INDEX IF NOT EXISTS idx_insights_entity_refs ON m1_insights.insights USING gin (entity_refs);",
    """
    CREATE TABLE IF NOT EXISTS m1_insights.reports (
        report_id       TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        body_md         TEXT NOT NULL,
        audience        TEXT NOT NULL DEFAULT 'general',
        insight_refs    JSONB NOT NULL DEFAULT '[]'::jsonb,
        status          TEXT NOT NULL DEFAULT 'draft',
        model           TEXT,
        engine_version  TEXT NOT NULL,
        generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_reports_status ON m1_insights.reports (status);",
]


def init_schema() -> None:
    with cursor() as cur:
        for statement in DDL:
            cur.execute(statement)
    log("m1_insights schema ready (insights, reports).")


if __name__ == "__main__":
    init_schema()
