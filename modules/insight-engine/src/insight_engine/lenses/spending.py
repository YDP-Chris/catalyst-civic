#!/usr/bin/env python
"""
Spending lens — money moving through the agenda.

Baseline (v0.1): scans agenda items for budget / appropriation / reserve
language, extracts dollar figures, and flags the largest individual line items
and the meetings carrying the most financial weight. Designed to be deepened
later with department-report figures and minutes reconciliation.

Read-only. Evidence links each flagged figure to its agenda item + meeting.
"""
from __future__ import annotations

import os
import re

from insight_engine.lenses.base import Lens
from insight_engine.models import SEVERITY_HIGH, SEVERITY_NOTABLE, Evidence, Insight

MONEY_KEYWORDS = (
    "budget", "appropriat", "reserve", "fund", "expenditure", "purchase",
    "contract", "bid", "grant", "tax", "fee", "revenue", "audit", "fiscal",
)
# Flag individual figures at or above this dollar amount as high severity.
HIGH_DOLLAR_THRESHOLD = float(os.getenv("CC_SPENDING_HIGH_THRESHOLD", "100000"))
TOP_N = int(os.getenv("CC_SPENDING_TOP_N", "20"))

DOLLAR_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]{2})?)")

# COALESCE across the agenda item text columns observed in the schema, so the
# lens works whether the loader populated `content`, `item_text`, or only title.
SCAN_SQL = """
SELECT
    i.item_id,
    i.meeting_id,
    COALESCE(i.title, i.label, '')                       AS item_title,
    COALESCE(i.content, i.item_text, i.title, i.label, '') AS item_body,
    m.meeting_date
FROM m1_agenda.items i
LEFT JOIN m1_agenda.meetings m ON m.meeting_id = i.meeting_id
WHERE COALESCE(i.content, i.item_text, i.title, i.label, '') ILIKE ANY(%(patterns)s)
"""


def _max_dollar(text: str) -> float:
    best = 0.0
    for match in DOLLAR_RE.finditer(text or ""):
        try:
            val = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        best = max(best, val)
    return best


class SpendingLens(Lens):
    name = "spending"
    description = "Budget, appropriation, and large-dollar agenda items."

    def analyze(self, cur) -> list[Insight]:
        patterns = [f"%{kw}%" for kw in MONEY_KEYWORDS]
        cur.execute(SCAN_SQL, {"patterns": patterns})
        rows = cur.fetchall()

        scored = []
        for row in rows:
            amount = _max_dollar(row["item_body"])
            if amount <= 0:
                continue
            scored.append((amount, row))

        scored.sort(key=lambda t: t[0], reverse=True)
        insights: list[Insight] = []

        for amount, row in scored[:TOP_N]:
            meeting_date = (
                row["meeting_date"].isoformat()
                if row.get("meeting_date") and hasattr(row["meeting_date"], "isoformat")
                else (str(row["meeting_date"]) if row.get("meeting_date") else None)
            )
            severity = SEVERITY_HIGH if amount >= HIGH_DOLLAR_THRESHOLD else SEVERITY_NOTABLE
            title_snip = (row["item_title"] or "Agenda item").strip()[:120]
            insights.append(
                Insight(
                    lens=self.name,
                    title=f"${amount:,.0f} — {title_snip}",
                    summary=(
                        f"Agenda item references a figure of approximately ${amount:,.2f}"
                        + (f" ({meeting_date})" if meeting_date else "")
                        + f". Item: {title_snip}."
                    ),
                    severity=severity,
                    confidence=0.6,
                    metrics={"amount_usd": amount, "meeting_date": meeting_date},
                    evidence=[
                        Evidence(
                            kind="agenda_item",
                            ref=str(row["item_id"]),
                            meeting_id=str(row["meeting_id"]) if row.get("meeting_id") else None,
                            meeting_date=meeting_date,
                            excerpt=(row["item_body"] or "")[:280],
                        )
                    ],
                    source_lane="m1_agenda.items",
                )
            )
        return insights
