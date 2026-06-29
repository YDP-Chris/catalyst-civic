#!/usr/bin/env python
"""
Surry County minutes ingester — documentary lane, spending + dispositions.

Minutes are born-digital (searchable) PDFs, so this extracts text directly
(pymupdf), with an OCR fallback for any page that lacks embedded text. The text
is split into excerpts (~120-word paragraph chunks that preserve sentences with
dollar figures and vote language) and loaded into m1_minutes.{meetings,excerpts}.
No LLM needed. meeting_id = SURRY_<date> so minutes share ids with the agenda
and transcript lanes.

The spending lens reads these excerpts (the agenda summaries omit dollar
amounts; the minutes carry them).

Usage:
  python ingest_minutes.py            # all in sources.json
  python ingest_minutes.py --date 2026-06-01
Reads PG_* from env. tesseract only needed if a page lacks embedded text.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import urllib.parse
from pathlib import Path

import fitz
import psycopg2
import psycopg2.extras
import requests

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"
RAW_DIR = HERE / "data" / "pdfs"
WORDS_PER_EXCERPT = 120


def _connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"], port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "postgres"), user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"], sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=20)


def _download(base: str, path: str, dest: Path) -> bool:
    r = requests.get(base.rstrip("/") + "/" + urllib.parse.quote(path), timeout=40)
    if r.status_code != 200 or not r.content:
        return False
    dest.write_bytes(r.content)
    return True


def _extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    out = []
    for page in doc:
        native = page.get_text().strip()
        if len(native) > 40:
            out.append(native)
        else:  # rare: scanned page in an otherwise-digital doc
            try:
                import pytesseract
                from PIL import Image
                pix = page.get_pixmap(dpi=300)
                out.append(pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png")))))
            except Exception:
                pass
    return "\n".join(out)


def _chunk(text: str) -> list[str]:
    """~120-word excerpts on paragraph boundaries, keeping money/vote sentences intact."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if p]
    excerpts, buf = [], []
    for p in paras:
        buf.append(p)
        if sum(len(x.split()) for x in buf) >= WORDS_PER_EXCERPT:
            excerpts.append(" ".join(buf)); buf = []
    if buf:
        excerpts.append(" ".join(buf))
    return excerpts


def ingest_one(entry: dict, src: dict, conn) -> str:
    date = entry["meeting_date"]
    meeting_id = f"SURRY_{date.replace('-', '_')}"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf = RAW_DIR / f"{meeting_id}.pdf"
    if not pdf.exists() and not _download(src["base_url"], entry["path"], pdf):
        return f"{meeting_id}: DOWNLOAD FAILED"
    text = _extract_text(pdf)
    if len(text.strip()) < 100:
        return f"{meeting_id}: NO TEXT"
    excerpts = _chunk(text)

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO m1_minutes.meetings (meeting_id, source_id, jurisdiction, meeting_type, meeting_date, is_complete)
        VALUES (%s,%s,%s,%s,%s,true)
        ON CONFLICT (meeting_id) DO UPDATE SET meeting_date=EXCLUDED.meeting_date;
    """, (meeting_id, entry["path"], src.get("jurisdiction", "Surry County"),
          src.get("meeting_type", "Board of Commissioners"), date))
    cur.execute("DELETE FROM m1_minutes.excerpts WHERE meeting_id=%s", (meeting_id,))
    rows = [(f"{meeting_id}_x{i}", meeting_id, i, ex) for i, ex in enumerate(excerpts)]
    psycopg2.extras.execute_values(cur,
        "INSERT INTO m1_minutes.excerpts (excerpt_id, meeting_id, ordinal, content) VALUES %s", rows)
    conn.commit(); cur.close()
    return f"{meeting_id}: {len(excerpts)} excerpts ({len(text.split())} words)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Surry minutes ingester")
    ap.add_argument("--date")
    args = ap.parse_args()
    src = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = src["minutes"]
    if args.date:
        entries = [e for e in entries if e["meeting_date"] == args.date]
    conn = _connect()
    for e in entries:
        try:
            print(ingest_one(e, src, conn), flush=True)
        except Exception as exc:
            print(f"{e['meeting_date']}: ERROR {type(exc).__name__}: {str(exc)[:160]}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
