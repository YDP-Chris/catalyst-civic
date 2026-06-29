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
TOP_N = int(os.getenv("CC_SPENDING_TOP_N", "25"))
# Floor out routine pennies/fees (tax refunds of $56.73, etc.) — keep substantive items.
MIN_AMOUNT = float(os.getenv("CC_SPENDING_MIN_AMOUNT", "5000"))

DOLLAR_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]{2})?)")
SENTENCE_RE = re.compile(r"(?<=[.;:!?])\s+")

# COALESCE across the agenda item text columns observed in the schema, so the
# lens works whether the loader populated `content`, `item_text`, or only title.
SCAN_SQL = """
SELECT
    i.item_id                                            AS ref,
    'agenda_item'                                        AS kind,
    i.meeting_id,
    COALESCE(i.title, i.label, '')                       AS item_title,
    COALESCE(i.content, i.item_text, i.title, i.label, '') AS item_body,
    m.meeting_date
FROM m1_agenda.items i
LEFT JOIN m1_agenda.meetings m ON m.meeting_id = i.meeting_id
WHERE COALESCE(i.content, i.item_text, i.title, i.label, '') ILIKE ANY(%(patterns)s)
"""

# Minutes carry the actual dollar figures and dispositions that agenda summaries
# omit, so the spending lens reads minutes excerpts too. Best-effort: skipped
# cleanly if the m1_minutes schema isn't present.
MINUTES_SQL = """
SELECT
    e.excerpt_id        AS ref,
    'minutes_excerpt'   AS kind,
    e.meeting_id,
    left(e.content, 90) AS item_title,
    e.content           AS item_body,
    m.meeting_date
FROM m1_minutes.excerpts e
LEFT JOIN m1_minutes.meetings m ON m.meeting_id = e.meeting_id
WHERE e.content ILIKE ANY(%(patterns)s)
"""


def _dollar_hits(text: str) -> list[tuple[float, str]]:
    """
    Each dollar figure tied to its LOCAL context: the sentence containing it,
    plus the preceding sentence (often the 'who/what'). This stops a large
    figure from being mis-attributed to unrelated text elsewhere in the excerpt.
    Returns (amount, context) for the largest figure in each money-bearing
    sentence.
    """
    sentences = SENTENCE_RE.split(re.sub(r"\s+", " ", text or "").strip())
    hits: list[tuple[float, str]] = []
    for i, s in enumerate(sentences):
        best = 0.0
        for m in DOLLAR_RE.finditer(s):
            try:
                best = max(best, float(m.group(1).replace(",", "")))
            except ValueError:
                continue
        if best >= MIN_AMOUNT:
            context = ((sentences[i - 1] + " ") if i > 0 else "") + s
            hits.append((best, context.strip()))
    return hits


class SpendingLens(Lens):
    name = "spending"
    description = "Budget, appropriation, and large-dollar agenda items."

    def analyze(self, cur) -> list[Insight]:
        patterns = [f"%{kw}%" for kw in MONEY_KEYWORDS]
        cur.execute(SCAN_SQL, {"patterns": patterns})
        rows = list(cur.fetchall())
        # Minutes are where the dollar figures actually live; include them if present.
        try:
            cur.execute(MINUTES_SQL, {"patterns": patterns})
            rows += list(cur.fetchall())
        except Exception:
            pass  # m1_minutes not present in this deployment

        # One candidate per money-bearing sentence, tied to its local context;
        # dedupe per (meeting, amount), keeping the richest context.
        best: dict[tuple, tuple] = {}
        for row in rows:
            for amount, context in _dollar_hits(row["item_body"]):
                key = (row.get("meeting_id"), round(amount, 2))
                prev = best.get(key)
                if prev is None or len(context) > len(prev[1]):
                    best[key] = (amount, context, row)

        candidates = sorted(best.values(), key=lambda t: t[0], reverse=True)[:TOP_N]
        insights: list[Insight] = []
        for amount, context, row in candidates:
            meeting_date = (
                row["meeting_date"].isoformat()
                if row.get("meeting_date") and hasattr(row["meeting_date"], "isoformat")
                else (str(row["meeting_date"]) if row.get("meeting_date") else None)
            )
            severity = SEVERITY_HIGH if amount >= HIGH_DOLLAR_THRESHOLD else SEVERITY_NOTABLE
            kind = row.get("kind", "agenda_item")
            where = "Minutes" if kind == "minutes_excerpt" else "Agenda item"
            insights.append(
                Insight(
                    lens=self.name,
                    title=f"${amount:,.0f} — {context[:120]}",
                    summary=(
                        f"{where}"
                        + (f" ({meeting_date})" if meeting_date else "")
                        + f" references ${amount:,.2f}. Context: {context[:400]}"
                    ),
                    severity=severity,
                    confidence=0.6,
                    metrics={"amount_usd": amount, "meeting_date": meeting_date, "source": kind},
                    evidence=[
                        Evidence(
                            kind=kind,
                            ref=str(row["ref"]),
                            meeting_id=str(row["meeting_id"]) if row.get("meeting_id") else None,
                            meeting_date=meeting_date,
                            excerpt=context[:400],
                        )
                    ],
                    source_lane="m1_minutes.excerpts" if kind == "minutes_excerpt" else "m1_agenda.items",
                )
            )
        return insights
