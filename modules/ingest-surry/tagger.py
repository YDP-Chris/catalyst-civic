#!/usr/bin/env python
"""
Surry County ingester — stage 4: ontology tagging (the "Palantir layer").

Reads reconstructed turns for a meeting from m1_transcript.turns, has Claude
extract the civic ONTOLOGY — objects (people, orgs, boards, locations, topics,
ordinances) and facts/relationships about them — each grounded in a specific
turn with a verbatim quote, and writes it to cco.{registry,identities,
observations} with provenance.

Provenance is mandatory: every observation carries source_id (meeting_id),
the turn ordinal it came from, and the verbatim quote. That is what lets a
researcher walk any influence-lens finding back to the exact moment in the
public meeting.

Model: defaults to claude-sonnet-4-6 (structured extraction; cheap at corpus
scale). Override with CC_TAG_MODEL. Idempotent per meeting (re-tagging replaces
that meeting's observations).

Usage:
  python tagger.py --meeting SURRY_2025_03_17 [--meeting SURRY_2025_02_17]
  python tagger.py --limit 2          # first N untagged meetings
Reads PG_* + ANTHROPIC_API_KEY from env.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import anthropic
import psycopg2
import psycopg2.extras

MODEL = os.getenv("CC_TAG_MODEL", "claude-sonnet-4-6")
CATEGORIES = ["PEOPLE", "ORGANIZATION", "BOARD", "AGENCY", "LOCATION", "TOPIC", "ORDINANCE", "OTHER"]
FACT_KEYS = ["MENTIONED_IN_RECORD", "MADE_MOTION", "SECONDED_MOTION", "VOTED", "ROLE",
             "AFFILIATION", "PROPERTY_ADDRESS", "APPLICANT", "TOPIC_DISCUSSED",
             "FUNDING_OR_SPENDING", "OTHER"]

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"entities": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "canonical_name": {"type": "string"},
            "category": {"type": "string", "enum": CATEGORIES},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "observations": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "fact": {"type": "string"},
                    "fact_key": {"type": "string", "enum": FACT_KEYS},
                    "evidence_turn": {"type": "integer"},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["fact", "fact_key", "evidence_turn", "evidence_quote"],
            }},
        },
        "required": ["canonical_name", "category", "aliases", "observations"],
    }}},
    "required": ["entities"],
}

SYSTEM = """You are a civic-records ontology extractor for a local-government \
transparency platform. You are given numbered transcript turns from a county \
Board of Commissioners meeting (auto-captioned, so names may be slightly \
misspelled — normalize obvious cases). Extract the entities that matter for \
civic accountability and the facts/relationships about each, STRICTLY grounded \
in the text.

Rules:
- Only extract what the turns support. Do not invent names, roles, dollar \
amounts, or relationships. If unsure, leave it out.
- Every observation must cite the turn number it came from and a short verbatim \
quote from that turn.
- Prefer named, consequential actors: commissioners, staff/officials, citizens \
who speak, organizations, boards/agencies, applicants, named places/parcels, \
ordinances/resolutions, and substantive topics.
- Resolve obvious alias variants to one canonical name; list the variants.
- Keep facts atomic and specific (one motion, one role, one funding item each)."""


def _connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"], port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "postgres"), user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"], sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=20)


def _registry_id(category: str, name: str) -> str:
    h = hashlib.sha256(f"{category}|{name.strip().lower()}".encode()).hexdigest()[:12]
    return f"reg_{h}"


def _load_turns(cur, meeting_id: str) -> tuple[list[tuple[int, str]], str | None]:
    cur.execute("select meeting_date::text from m1_transcript.meetings where meeting_id=%s", (meeting_id,))
    row = cur.fetchone()
    mdate = row[0] if row else None
    cur.execute("select ordinal, content from m1_transcript.turns where meeting_id=%s order by ordinal", (meeting_id,))
    return [(r[0], r[1]) for r in cur.fetchall()], mdate


def tag_meeting(meeting_id: str, conn, client) -> dict:
    cur = conn.cursor()
    turns, mdate = _load_turns(cur, meeting_id)
    if not turns:
        return {"meeting_id": meeting_id, "status": "no_turns"}

    numbered = "\n".join(f"{o}: {t}" for o, t in turns)
    user = (f"Meeting: {meeting_id} ({mdate or 'date unknown'})\n\n"
            f"Transcript turns (numbered):\n{numbered}\n\n"
            "Extract the civic ontology as specified.")

    # No thinking: structured extraction is pattern work, not reasoning, and
    # thinking would eat the token budget before the JSON is emitted.
    msg = client.messages.create(
        model=MODEL, max_tokens=16000,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )
    texts = [b.text for b in msg.content if b.type == "text"]
    if not texts:
        raise RuntimeError(f"no text block (stop_reason={msg.stop_reason})")
    data = json.loads(texts[0])
    entities = data.get("entities", [])

    # idempotent: clear this meeting's prior observations
    cur.execute("delete from cco.observations where source_id=%s", (meeting_id,))

    reg_rows, id_rows, obs_rows = [], [], []
    for e in entities:
        rid = _registry_id(e["category"], e["canonical_name"])
        reg_rows.append((rid, e["category"], e["canonical_name"]))
        for alias in set([e["canonical_name"], *e.get("aliases", [])]):
            id_rows.append((rid, alias, meeting_id))
        for o in e.get("observations", []):
            obs_rows.append((rid, o["fact_key"],
                             json.dumps({"fact": o["fact"], "turn": o["evidence_turn"]}),
                             meeting_id, o["evidence_quote"][:500], mdate))

    psycopg2.extras.execute_values(cur,
        "insert into cco.registry (registry_id,category,canonical_name) values %s "
        "on conflict (registry_id) do update set canonical_name=excluded.canonical_name", reg_rows)
    psycopg2.extras.execute_values(cur,
        "insert into cco.identities (registry_id,alias_name,source_id) values %s "
        "on conflict (registry_id,alias_name) do nothing", id_rows)
    psycopg2.extras.execute_values(cur,
        "insert into cco.observations (registry_id,fact_key,fact_value,source_id,evidence,effective_date) values %s",
        obs_rows)
    conn.commit(); cur.close()
    return {"meeting_id": meeting_id, "status": "tagged",
            "entities": len(reg_rows), "observations": len(obs_rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Surry ingester stage 4 (ontology tagging)")
    ap.add_argument("--meeting", action="append", help="meeting_id (repeatable)")
    ap.add_argument("--limit", type=int, help="tag the first N transcript meetings")
    args = ap.parse_args()

    conn = _connect(); cur = conn.cursor()
    if args.meeting:
        meetings = args.meeting
    else:
        cur.execute("select meeting_id from m1_transcript.meetings where meeting_id like 'SURRY%' order by meeting_date desc nulls last")
        meetings = [r[0] for r in cur.fetchall()]
        if args.limit:
            meetings = meetings[:args.limit]
    cur.close()

    client = anthropic.Anthropic()
    for m in meetings:
        try:
            r = tag_meeting(m, conn, client)
            print(f"  {r['meeting_id']}: {r['status']}"
                  + (f" -> {r.get('entities',0)} entities, {r.get('observations',0)} observations" if r['status']=='tagged' else ""))
        except Exception as exc:
            print(f"  {m}: ERROR {type(exc).__name__}: {str(exc)[:160]}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
