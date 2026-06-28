#!/usr/bin/env python
"""
Votes lens — how decisions got made.

Baseline (v0.1): uses the PRATTLE procedural phase tagging on transcript turns
to find the meetings with the heaviest motion/vote activity (a proxy for
contested or consequential sessions), and summarizes the disposition mix across
processed meetings. Designed to be deepened into per-item pass/fail/tabled
tracking and split-vote detection as disposition data firms up.

Read-only. Evidence links to the transcript meeting and sample procedural turns.
"""
from __future__ import annotations

import os

from insight_engine.lenses.base import Lens
from insight_engine.models import SEVERITY_HIGH, SEVERITY_NOTABLE, Evidence, Insight

MIN_PROCEDURAL_TURNS = int(os.getenv("CC_VOTES_MIN_TURNS", "8"))
HIGH_PROCEDURAL_TURNS = int(os.getenv("CC_VOTES_HIGH_THRESHOLD", "25"))
TOP_N = int(os.getenv("CC_VOTES_TOP_N", "15"))

# Phase labels from the Roberts Rules state machine that indicate decision activity.
PROCEDURAL_PATTERNS = ["%vote%", "%motion%", "%second%", "%amend%", "%adopt%", "%resolv%"]

ACTIVITY_SQL = """
SELECT
    t.meeting_id,
    COUNT(*) AS procedural_turns,
    m.meeting_date,
    m.disposition_code
FROM m1_transcript.turns t
LEFT JOIN m1_transcript.meetings m ON m.meeting_id = t.meeting_id
WHERE t.phase ILIKE ANY(%(patterns)s)
GROUP BY t.meeting_id, m.meeting_date, m.disposition_code
HAVING COUNT(*) >= %(min_turns)s
ORDER BY procedural_turns DESC
LIMIT %(top_n)s;
"""

SAMPLE_TURNS_SQL = """
SELECT t.turn_row_id, t.phase, t.speaker_name, t.content
FROM m1_transcript.turns t
WHERE t.meeting_id = %(meeting_id)s AND t.phase ILIKE ANY(%(patterns)s)
ORDER BY t.ordinal
LIMIT 4;
"""


def _fmt(d) -> str | None:
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


class VotesLens(Lens):
    name = "votes"
    description = "Meetings with the heaviest motion/vote activity."

    def analyze(self, cur) -> list[Insight]:
        cur.execute(
            ACTIVITY_SQL,
            {
                "patterns": PROCEDURAL_PATTERNS,
                "min_turns": MIN_PROCEDURAL_TURNS,
                "top_n": TOP_N,
            },
        )
        rows = cur.fetchall()
        insights: list[Insight] = []

        for row in rows:
            meeting_id = row["meeting_id"]
            count = row["procedural_turns"]
            meeting_date = _fmt(row.get("meeting_date"))

            cur.execute(
                SAMPLE_TURNS_SQL,
                {"meeting_id": meeting_id, "patterns": PROCEDURAL_PATTERNS},
            )
            evidence = [
                Evidence(
                    kind="transcript_turn",
                    ref=str(s["turn_row_id"]),
                    meeting_id=str(meeting_id),
                    meeting_date=meeting_date,
                    excerpt=(
                        f"[{s.get('phase', '')}] "
                        f"{s.get('speaker_name') or 'Unknown'}: "
                        f"{(s.get('content') or '')[:200]}"
                    ),
                )
                for s in cur.fetchall()
            ]

            severity = SEVERITY_HIGH if count >= HIGH_PROCEDURAL_TURNS else SEVERITY_NOTABLE
            insights.append(
                Insight(
                    lens=self.name,
                    title=(
                        f"High decision activity: meeting {meeting_id}"
                        + (f" ({meeting_date})" if meeting_date else "")
                    ),
                    summary=(
                        f"This session carried {count} procedural (motion/vote/amendment) "
                        f"turns, among the most decision-dense meetings in the transcript "
                        f"corpus. Disposition: {row.get('disposition_code') or 'n/a'}."
                    ),
                    severity=severity,
                    confidence=0.55,
                    metrics={
                        "procedural_turns": count,
                        "meeting_date": meeting_date,
                        "disposition_code": row.get("disposition_code"),
                    },
                    evidence=evidence,
                    source_lane="m1_transcript.turns",
                )
            )
        return insights
