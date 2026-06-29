#!/usr/bin/env python
"""
Surry transcript SLOW harvester — reach full coverage past YouTube's IP block.

Bulk fetching trips YouTube's anti-bot rate limit (it blocked the Pi after ~40
rapid pulls). This harvester instead grabs a small batch per run with long
jittered delays, backs off cleanly the moment a block is detected, and is meant
to run on a cron every couple hours so the remaining ~80 meetings accumulate
over a day or two. Idempotent: skips already-staged meetings and remembers ones
with no transcript so it never retries them.

Each newly fetched meeting is reconstructed into m1_transcript immediately
(free). Pass --tag to also run the ontology tagger on new meetings (costs Sonnet
tokens; off by default).

Usage:
  python harvest.py                 # one batch (default 5), reconstruct new
  python harvest.py --batch 8 --tag
Loads PG_*/ANTHROPIC from the shared .env automatically; no shell sourcing.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"
RAW_DIR = HERE / "data" / "raw"
STATE = HERE / "data" / "harvest_state.json"
SHARED_ENV = Path("/home/ydp-admin/agents/.env")
PYTHON = sys.executable


def _load_env() -> None:
    """Load KEY=VALUE lines from the shared .env into os.environ (cron-safe)."""
    if not SHARED_ENV.exists():
        return
    for line in SHARED_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _staged_ids() -> set[str]:
    return {p.stem for p in RAW_DIR.glob("*.json")}


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"no_transcript": [], "last_block_at": None}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def _fetch_segments(video_id: str):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    if hasattr(api, "fetch"):
        return [{"start": s.start, "duration": s.duration, "text": s.text} for s in api.fetch(video_id)]
    return YouTubeTranscriptApi.get_transcript(video_id)


def main() -> int:
    ap = argparse.ArgumentParser(description="Surry transcript slow harvester")
    ap.add_argument("--batch", type=int, default=int(os.getenv("CC_HARVEST_BATCH", "5")))
    ap.add_argument("--min-delay", type=float, default=float(os.getenv("CC_HARVEST_MIN_DELAY", "25")))
    ap.add_argument("--max-delay", type=float, default=float(os.getenv("CC_HARVEST_MAX_DELAY", "55")))
    ap.add_argument("--tag", action="store_true", help="also tag new meetings (costs tokens)")
    args = ap.parse_args()

    _load_env()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text())
    state = _load_state()
    skip = _staged_ids() | set(state["no_transcript"])
    remaining = [v for v in sources["videos"] if v["video_id"] not in skip]
    print(f"coverage: {len(_staged_ids())} staged / {sources['count']} total | {len(remaining)} remaining")
    if not remaining:
        print("All meetings harvested.")
        return 0

    fetched = []
    for i, v in enumerate(remaining[:args.batch]):
        vid = v["video_id"]
        try:
            segs = _fetch_segments(vid)
            words = sum(len(s["text"].split()) for s in segs)
            (RAW_DIR / f"{vid}.json").write_text(json.dumps({
                "video_id": vid, "source_url": f"https://www.youtube.com/watch?v={vid}",
                "jurisdiction": "Surry County", "meeting_type": v.get("meeting_type"),
                "title": v.get("title"), "meeting_date": v.get("meeting_date"),
                "segment_count": len(segs), "word_count": words, "segments": segs,
            }, indent=2))
            print(f"  staged {vid} ({v.get('meeting_date')}): {len(segs)} segs / ~{words} words")
            fetched.append(v)
        except Exception as exc:
            name = type(exc).__name__
            if "IpBlocked" in name or "TooManyRequests" in name or "blocking" in str(exc).lower():
                print(f"  IP-BLOCK hit at {vid}; backing off, will resume next run.")
                state["last_block_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                break
            if "NoTranscript" in name or "TranscriptsDisabled" in name or "Unavailable" in name:
                print(f"  {vid}: no transcript ({name}); marking to skip permanently.")
                state["no_transcript"].append(vid)
            else:
                print(f"  {vid}: ERROR {name}: {str(exc)[:120]}")
        if i < min(args.batch, len(remaining)) - 1:
            time.sleep(random.uniform(args.min_delay, args.max_delay))
    _save_state(state)

    # reconstruct the freshly fetched meetings (free, idempotent)
    for v in fetched:
        subprocess.run([PYTHON, str(HERE / "reconstruct.py"), "--video", v["video_id"]], env=os.environ)
    if args.tag and fetched:
        for v in fetched:
            mid = f"SURRY_{v['meeting_date'].replace('-', '_')}" if v.get("meeting_date") else f"SURRY_{v['video_id']}"
            subprocess.run([PYTHON, str(HERE / "tagger.py"), "--meeting", mid], env=os.environ)

    still = len(remaining) - len(fetched)
    print(f"\nharvested {len(fetched)} this run; {still} remaining. "
          + ("Run again (cron) to continue." if still else "Coverage complete."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
