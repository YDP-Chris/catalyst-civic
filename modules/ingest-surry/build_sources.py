#!/usr/bin/env python
"""
Surry County ingester — build the source index.

Enumerates the Surry County Board of Commissioners YouTube channel (meetings are
livestreams, so they live under the /streams tab) and writes sources.json: one
entry per meeting with video_id, parsed meeting_date, meeting_type, and title.

Uses yt-dlp for enumeration only (no media download). Re-run to refresh as new
meetings post.

Usage:
  python build_sources.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHANNEL = "https://www.youtube.com/@surrycountynccommissioners/streams"
OUT = HERE / "sources.json"

MONTHS = {m: i for i, m in enumerate(
    ["january","february","march","april","may","june","july","august",
     "september","october","november","december"], start=1)}
DATE_RE = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(\d{1,2}),?\s+(\d{4})", re.I)


def parse_date(title: str) -> str | None:
    m = DATE_RE.search(title)
    if not m:
        return None
    mon = MONTHS[m.group(1).lower()]
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"


def classify(title: str) -> str:
    t = title.lower()
    if "budget workshop" in t:
        return "Budget Workshop"
    if "retreat" in t:
        return "Retreat"
    if "special" in t:
        return "Special Meeting"
    return "Board of Commissioners"


def enumerate_channel() -> list[dict]:
    raw = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--flat-playlist", "--no-warnings",
         "--print", "%(id)s\t%(title)s", CHANNEL],
        capture_output=True, text=True,
    ).stdout
    videos = []
    for line in raw.splitlines():
        if "\t" not in line:
            continue
        vid, title = line.split("\t", 1)
        title = title.strip()
        # skip non-meeting placeholder rows
        if "Board of Commissioners" not in title and "Budget Workshop" not in title:
            continue
        videos.append({
            "video_id": vid.strip(),
            "meeting_date": parse_date(title),
            "meeting_type": classify(title),
            "title": title,
        })
    return videos


def main() -> int:
    videos = enumerate_channel()
    if not videos:
        print("No meetings enumerated (yt-dlp returned nothing usable).")
        return 1
    dated = sum(1 for v in videos if v["meeting_date"])
    doc = {
        "channel": CHANNEL,
        "jurisdiction": "Surry County",
        "count": len(videos),
        "videos": sorted(videos, key=lambda v: v["meeting_date"] or "", reverse=True),
    }
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"Wrote {len(videos)} meetings to sources.json ({dated} with parsed dates).")
    by_type: dict[str, int] = {}
    for v in videos:
        by_type[v["meeting_type"]] = by_type.get(v["meeting_type"], 0) + 1
    print("by type:", by_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
