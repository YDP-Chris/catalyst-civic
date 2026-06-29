#!/usr/bin/env python
"""
Surry County transcript ingester — stage 1: fetch raw transcripts.

Pulls public auto-generated transcripts for Surry County Board of Commissioners
meetings (YouTube) and stages them to data/raw/<video_id>.json. This is the raw,
speaker-blind, phonetically-noisy input — the same kind of stream the Catalyst
PRATTLE engine reconstructs. Reconstruction + speaker attribution + ontology
tagging are later stages (see README).

Read-only against YouTube; idempotent (skips already-staged videos unless
--force). No DB needed for this stage.

Usage:
  python fetch_transcripts.py                 # fetch all in sources.json
  python fetch_transcripts.py --video FRNjggFp0_M
  python fetch_transcripts.py --force
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: youtube-transcript-api. "
        "Install in the project venv: .venv/bin/pip install youtube-transcript-api"
    ) from exc

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"
RAW_DIR = HERE / "data" / "raw"


def _fetch_segments(video_id: str) -> list[dict]:
    """Return [{start, duration, text}] across library versions (API has changed)."""
    api = YouTubeTranscriptApi()
    if hasattr(api, "fetch"):  # newer instance API
        fetched = api.fetch(video_id)
        return [{"start": s.start, "duration": s.duration, "text": s.text} for s in fetched]
    return YouTubeTranscriptApi.get_transcript(video_id)  # older classmethod API


def fetch_one(video: dict, force: bool) -> str:
    vid = video["video_id"]
    out = RAW_DIR / f"{vid}.json"
    if out.exists() and not force:
        return f"skip {vid} (already staged)"

    segments = _fetch_segments(vid)
    words = sum(len(s["text"].split()) for s in segments)
    record = {
        "video_id": vid,
        "source_url": f"https://www.youtube.com/watch?v={vid}",
        "jurisdiction": "Surry County",
        "meeting_type": "Board of Commissioners",
        "meeting_date": video.get("meeting_date"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "segment_count": len(segments),
        "word_count": words,
        "segments": segments,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return f"staged {vid}: {len(segments)} segments / ~{words} words -> {out.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Surry transcript ingester (fetch)")
    parser.add_argument("--video", help="Fetch a single video_id")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if staged")
    args = parser.parse_args()

    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    videos = sources["videos"]
    if args.video:
        videos = [v for v in videos if v["video_id"] == args.video] or [{"video_id": args.video}]

    for v in videos:
        try:
            print(fetch_one(v, args.force))
        except Exception as exc:
            print(f"ERROR {v.get('video_id')}: {type(exc).__name__}: {str(exc)[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
