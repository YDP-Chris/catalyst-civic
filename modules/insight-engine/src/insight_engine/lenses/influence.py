#!/usr/bin/env python
"""
Influence lens — "who keeps showing up."

Mines the authority layer (cco.registry + cco.observations) to surface civic
actors and organizations that recur across the public record. The more
distinct records an entity is observed in, the more central it is to local
government activity — exactly the thread a journalist or attorney pulls on
first ("show me everyone connected to this developer / this parcel / this
board over the last decade").

Read-only. Every insight carries observation-level evidence (fact_id +
source_id), so each named entity can be walked straight back to the records
that mention it.
"""
from __future__ import annotations

import os

from insight_engine.lenses.base import Lens
from insight_engine.models import (
    SEVERITY_HIGH,
    SEVERITY_NOTABLE,
    Evidence,
    Insight,
)

# Categories worth flagging as "actors" (people/orgs/developers), as opposed to
# procedural or reference categories that recur by construction.
ACTOR_CATEGORIES = ("PEOPLE", "ORGANIZATION", "BOARD", "AGENCY")

# Tunables (overridable via env so a deployment can dial sensitivity).
MIN_RECORDS = int(os.getenv("CC_INFLUENCE_MIN_RECORDS", "5"))
TOP_N = int(os.getenv("CC_INFLUENCE_TOP_N", "25"))
HIGH_RECORD_THRESHOLD = int(os.getenv("CC_INFLUENCE_HIGH_THRESHOLD", "20"))
EVIDENCE_PER_INSIGHT = 5

RANK_SQL = """
SELECT
    r.registry_id,
    r.canonical_name,
    r.category,
    COUNT(DISTINCT o.source_id) AS record_count,
    COUNT(o.fact_id)            AS observation_count,
    COUNT(DISTINCT o.fact_key)  AS fact_kind_count
FROM cco.registry r
JOIN cco.observations o ON o.registry_id = r.registry_id
WHERE r.category = ANY(%(categories)s)
GROUP BY r.registry_id, r.canonical_name, r.category
HAVING COUNT(DISTINCT o.source_id) >= %(min_records)s
ORDER BY record_count DESC, observation_count DESC
LIMIT %(top_n)s;
"""

EVIDENCE_SQL = """
SELECT
    o.fact_id,
    o.fact_key,
    o.source_id,
    o.evidence,
    o.fact_value
FROM cco.observations o
WHERE o.registry_id = %(registry_id)s
ORDER BY o.created_at DESC
LIMIT %(limit)s;
"""

ALIAS_SQL = """
SELECT alias_name
FROM cco.identities
WHERE registry_id = %(registry_id)s
ORDER BY alias_name
LIMIT 10;
"""


def _excerpt(row) -> str:
    """Best-effort human-readable snippet from an observation row."""
    if row.get("evidence"):
        return str(row["evidence"])[:280]
    fv = row.get("fact_value")
    if isinstance(fv, dict):
        ctx = fv.get("context") or fv.get("role") or ""
        if ctx:
            return str(ctx)[:280]
    return f"{row.get('fact_key', 'observation')} (source {row.get('source_id', 'unknown')})"


class InfluenceLens(Lens):
    name = "influence"
    description = "Recurring civic actors and organizations across the authority layer."

    def analyze(self, cur) -> list[Insight]:
        cur.execute(
            RANK_SQL,
            {
                "categories": list(ACTOR_CATEGORIES),
                "min_records": MIN_RECORDS,
                "top_n": TOP_N,
            },
        )
        ranked = cur.fetchall()
        insights: list[Insight] = []

        for row in ranked:
            registry_id = row["registry_id"]
            name = row["canonical_name"]
            category = row["category"]
            record_count = row["record_count"]
            observation_count = row["observation_count"]

            # Pull aliases (helps a researcher see name variants in one place).
            cur.execute(ALIAS_SQL, {"registry_id": registry_id})
            aliases = [a["alias_name"] for a in cur.fetchall()]

            # Pull supporting evidence.
            cur.execute(
                EVIDENCE_SQL,
                {"registry_id": registry_id, "limit": EVIDENCE_PER_INSIGHT},
            )
            evidence = [
                Evidence(
                    kind="observation",
                    ref=str(e["fact_id"]),
                    source_id=e.get("source_id"),
                    excerpt=_excerpt(e),
                )
                for e in cur.fetchall()
            ]

            severity = (
                SEVERITY_HIGH
                if record_count >= HIGH_RECORD_THRESHOLD
                else SEVERITY_NOTABLE
            )
            # Confidence scales with how broadly the entity recurs, capped.
            confidence = min(0.95, 0.4 + record_count / 100.0)

            alias_note = (
                f" Also recorded as: {', '.join(aliases[:5])}." if len(aliases) > 1 else ""
            )
            summary = (
                f"{name} ({category.title()}) appears across {record_count} distinct "
                f"records with {observation_count} recorded observations, making it one "
                f"of the most frequently referenced actors in the civic corpus.{alias_note}"
            )

            insights.append(
                Insight(
                    lens=self.name,
                    title=f"Recurring actor: {name}",
                    summary=summary,
                    severity=severity,
                    confidence=round(confidence, 2),
                    entity_refs=[str(registry_id)],
                    metrics={
                        "record_count": record_count,
                        "observation_count": observation_count,
                        "fact_kind_count": row["fact_kind_count"],
                        "category": category,
                        "alias_count": len(aliases),
                    },
                    evidence=evidence,
                    source_lane="cco.observations",
                )
            )

        return insights
