#!/usr/bin/env python
"""
Topics lens — what the council keeps coming back to.

Baseline (v0.1): counts how many distinct meetings each civic topic appears in,
using a municipal topic lexicon matched against agenda item text, and reports
the date span. A topic that recurs across many meetings over many years is a
running thread in local government — the kind of pattern that's invisible when
records are siloed per-meeting.

Read-only. Evidence links each topic to sample agenda items.
"""
from __future__ import annotations

import os

from insight_engine.lenses.base import Lens
from insight_engine.models import SEVERITY_HIGH, SEVERITY_NOTABLE, Evidence, Insight

# Municipal topic lexicon: label -> ILIKE patterns that signal it.
TOPIC_LEXICON: dict[str, list[str]] = {
    "Rezoning & land use": ["%rezon%", "%zoning%", "%land use%", "%variance%", "%subdivision%"],
    "Water & sewer": ["%water%", "%sewer%", "%wastewater%", "%utility%", "%utilities%"],
    "Public safety": ["%police%", "%fire dep%", "%emergency%", "%public safety%"],
    "Roads & infrastructure": ["%street%", "%road%", "%paving%", "%sidewalk%", "%infrastructure%"],
    "Budget & taxes": ["%budget%", "%tax rate%", "%millage%", "%appropriat%", "%fiscal year%"],
    "Economic development": ["%economic develop%", "%incentive%", "%industrial park%", "%annexation%"],
    "Housing": ["%housing%", "%residential%", "%apartment%", "%development%"],
    "Personnel & administration": ["%personnel%", "%hiring%", "%salary%", "%appointment%"],
}

MIN_MEETINGS = int(os.getenv("CC_TOPICS_MIN_MEETINGS", "5"))
HIGH_MEETING_THRESHOLD = int(os.getenv("CC_TOPICS_HIGH_THRESHOLD", "40"))
EVIDENCE_PER_TOPIC = 4

COUNT_SQL = """
SELECT
    COUNT(DISTINCT i.meeting_id) AS meeting_count,
    MIN(m.meeting_date)          AS first_date,
    MAX(m.meeting_date)          AS last_date
FROM m1_agenda.items i
LEFT JOIN m1_agenda.meetings m ON m.meeting_id = i.meeting_id
WHERE COALESCE(i.content, i.item_text, i.title, i.label, '') ILIKE ANY(%(patterns)s);
"""

SAMPLE_SQL = """
SELECT i.item_id, i.meeting_id, COALESCE(i.title, i.label, '') AS item_title, m.meeting_date
FROM m1_agenda.items i
LEFT JOIN m1_agenda.meetings m ON m.meeting_id = i.meeting_id
WHERE COALESCE(i.content, i.item_text, i.title, i.label, '') ILIKE ANY(%(patterns)s)
ORDER BY m.meeting_date DESC NULLS LAST
LIMIT %(limit)s;
"""


def _fmt(d) -> str | None:
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


class TopicsLens(Lens):
    name = "topics"
    description = "Recurring agenda topics and how long they have persisted."

    def analyze(self, cur) -> list[Insight]:
        insights: list[Insight] = []
        for topic, patterns in TOPIC_LEXICON.items():
            cur.execute(COUNT_SQL, {"patterns": patterns})
            agg = cur.fetchone()
            meeting_count = (agg or {}).get("meeting_count") or 0
            if meeting_count < MIN_MEETINGS:
                continue

            first_date = _fmt((agg or {}).get("first_date"))
            last_date = _fmt((agg or {}).get("last_date"))

            cur.execute(SAMPLE_SQL, {"patterns": patterns, "limit": EVIDENCE_PER_TOPIC})
            evidence = [
                Evidence(
                    kind="agenda_item",
                    ref=str(s["item_id"]),
                    meeting_id=str(s["meeting_id"]) if s.get("meeting_id") else None,
                    meeting_date=_fmt(s.get("meeting_date")),
                    excerpt=(s["item_title"] or "")[:200],
                )
                for s in cur.fetchall()
            ]

            severity = (
                SEVERITY_HIGH if meeting_count >= HIGH_MEETING_THRESHOLD else SEVERITY_NOTABLE
            )
            span = (
                f" spanning {first_date} to {last_date}"
                if first_date and last_date
                else ""
            )
            insights.append(
                Insight(
                    lens=self.name,
                    title=f"Recurring topic: {topic}",
                    summary=(
                        f"'{topic}' appears on the agenda across {meeting_count} distinct "
                        f"meetings{span}, marking it as a persistent thread in council activity."
                    ),
                    severity=severity,
                    confidence=0.6,
                    metrics={
                        "meeting_count": meeting_count,
                        "first_date": first_date,
                        "last_date": last_date,
                    },
                    evidence=evidence,
                    source_lane="m1_agenda.items",
                )
            )
        return insights
