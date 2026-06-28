#!/usr/bin/env python
"""
Core data model for the Insight Engine.

An Insight is one structured, evidence-backed finding produced by a lens. The
defining rule of this engine: nothing is an insight unless it carries Evidence
that points back to a concrete source record (a meeting, an agenda item, a
transcript turn, or an authority observation). That traceability is what makes
the output usable for civic research, legal discovery, and journalism — every
claim can be walked back to the public record it came from.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any

ENGINE_VERSION = "insight.engine.v0.1"

# Severity ladder. `notable` is the default; lenses escalate to `high` only
# when a finding is materially unusual (large dollar figure, sharp spike, etc.).
SEVERITY_INFO = "info"
SEVERITY_NOTABLE = "notable"
SEVERITY_HIGH = "high"


@dataclass
class Evidence:
    """
    A single pointer back into the source record that supports an Insight.

    kind     : which source lane the reference lives in
               (agenda_item | transcript_turn | observation | meeting | document)
    source_id: the pipeline source/run id the record was ingested under
    ref       : the primary key of the source row (item_id, turn_row_id, fact_id, meeting_id, ...)
    meeting_id: the meeting this evidence is anchored to, when known
    excerpt   : short human-readable snippet for the report writer to quote
    """

    kind: str
    ref: str
    excerpt: str = ""
    source_id: str | None = None
    meeting_id: str | None = None
    meeting_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Insight:
    """One structured finding from a lens."""

    lens: str
    title: str
    summary: str
    severity: str = SEVERITY_NOTABLE
    confidence: float = 0.5
    entity_refs: list[str] = field(default_factory=list)  # cco.registry_id values
    metrics: dict[str, Any] = field(default_factory=dict)  # the computed numbers
    evidence: list[Evidence] = field(default_factory=list)
    source_lane: str = "insight_engine"

    def dedupe_key(self) -> str:
        """
        Stable key so re-runs upsert instead of duplicating. Built from the
        lens + the sorted entity set + a normalized title, so the same finding
        on the same entities maps to the same row across runs.
        """
        basis = json.dumps(
            {
                "lens": self.lens,
                "entities": sorted(self.entity_refs),
                "title": self.title.strip().lower(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]

    def insight_id(self) -> str:
        return f"INS_{self.lens.upper()}_{self.dedupe_key()[:12]}"

    def evidence_json(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.evidence]
