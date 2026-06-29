#!/usr/bin/env python
"""
Surry County ingester — stage 2: reconstruct turns.

Turns raw YouTube auto-caption fragments (data/raw/<vid>.json) into structured
transcript turns and loads them into m1_transcript.{meetings,turns}. No LLM:
this is deterministic chunking + Roberts-Rules phase tagging by keyword. Speaker
attribution is left to stage 4 (auto-captions carry no speaker labels).

Idempotent: re-running a meeting replaces its turns.

Usage:
  python reconstruct.py                 # process all usable staged meetings
  python reconstruct.py --video FRNjggFp0_M
Reads PG_* env vars (pooler connection).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from pathlib import Path

import psycopg2
import psycopg2.extras

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "data" / "raw"
WORDS_PER_TURN = 55
GAP_SECONDS = 3.0

# Roberts-Rules phase cues -> phase label (checked in order; first hit wins).
# Labels are chosen so the votes lens patterns (%vote/%motion/%second/%amend/%adopt) match.
PHASE_CUES = [
    ("OPENING",        ["call to order", "pledge of allegiance", "invocation"]),
    ("PUBLIC_COMMENT", ["public comment", "public hearing", "public forum"]),
    ("AMENDMENT",      ["amend"]),
    ("MOTION",         ["i move", "move to", "motion to", "make a motion", "a motion"]),
    ("SECOND",         ["i second", "second the motion", "i'll second"]),
    ("VOTE",           ["all in favor", "those opposed", "motion carries", "motion passes",
                        "motion fails", "all those in favor", "any opposed"]),
    ("ADOPTION",       ["adopt", "resolution", "be it resolved"]),
    ("ADJOURN",        ["adjourn"]),
]


def _connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"], port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "postgres"), user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"], sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=20,
    )


def _phase(text: str) -> str:
    low = text.lower()
    for label, cues in PHASE_CUES:
        if any(c in low for c in cues):
            return label
    return "DISCUSSION"


def _chunk_turns(segments: list[dict]) -> list[dict]:
    """Merge caption fragments into ~WORDS_PER_TURN-word turns, splitting on long gaps."""
    turns, buf, buf_start, last_end = [], [], None, None
    def flush():
        if buf:
            text = " ".join(buf).strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                turns.append({"start": buf_start, "text": text})
    for s in segments:
        st = s.get("start", 0.0)
        if buf and last_end is not None and (st - last_end) > GAP_SECONDS and len(" ".join(buf).split()) > 15:
            flush(); buf, buf_start = [], None
        if buf_start is None:
            buf_start = st
        buf.append(s["text"].replace("\n", " "))
        last_end = st + s.get("duration", 0.0)
        if len(" ".join(buf).split()) >= WORDS_PER_TURN:
            flush(); buf, buf_start = [], None
    flush()
    return turns


def reconstruct(rec: dict) -> tuple[str, list[dict]]:
    vid = rec["video_id"]
    date = rec.get("meeting_date")
    meeting_id = f"SURRY_{date.replace('-', '_')}" if date else f"SURRY_{vid}"
    raw_turns = _chunk_turns(rec["segments"])
    turns = []
    for i, t in enumerate(raw_turns):
        turns.append({
            "turn_id": f"{vid}_{i}",
            "ordinal": i,
            "phase": _phase(t["text"]),
            "content": t["text"],
        })
    return meeting_id, turns


def load(rec: dict, conn) -> str:
    meeting_id, turns = reconstruct(rec)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO m1_transcript.meetings
            (meeting_id, source_id, jurisdiction, meeting_date, disposition_code, total_turns)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (meeting_id) DO UPDATE SET total_turns=EXCLUDED.total_turns,
            meeting_date=EXCLUDED.meeting_date, disposition_code=EXCLUDED.disposition_code;
    """, (meeting_id, rec["video_id"], rec.get("jurisdiction", "Surry County"),
          rec.get("meeting_date"), "RAW_AUTOCAPTION", len(turns)))
    cur.execute("DELETE FROM m1_transcript.turns WHERE meeting_id=%s", (meeting_id,))
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO m1_transcript.turns (meeting_id, turn_id, ordinal, phase, content) VALUES %s",
        [(meeting_id, t["turn_id"], t["ordinal"], t["phase"], t["content"]) for t in turns],
        page_size=500,
    )
    conn.commit(); cur.close()
    proc = sum(1 for t in turns if t["phase"] in ("MOTION","SECOND","VOTE","AMENDMENT","ADOPTION"))
    return f"{meeting_id}: {len(turns)} turns ({proc} procedural)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Surry ingester stage 2 (reconstruct)")
    ap.add_argument("--video")
    args = ap.parse_args()
    files = sorted(glob.glob(str(RAW_DIR / "*.json")))
    conn = _connect()
    n = 0
    for f in files:
        rec = json.loads(Path(f).read_text())
        if rec.get("segment_count", 0) <= 50:
            continue
        if args.video and rec["video_id"] != args.video:
            continue
        print(load(rec, conn)); n += 1
    conn.close()
    print(f"\nloaded {n} meeting(s) into m1_transcript.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
