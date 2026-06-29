#!/usr/bin/env python
"""
Surry County agenda ingester — the documentary lane.

Free OCR path: download scanned agenda PDFs, rasterize + Tesseract OCR (local,
$0), then a cheap Haiku pass structures the OCR text into agenda items, loaded
into m1_agenda.{meetings,items}. meeting_id is SURRY_<date> so the agenda shares
ids with the transcript lane (the spoken + documentary records cross-link by
meeting).

Vision fallback is intentionally NOT here — OCR tested clean on these agendas.
If a future scan is too poor for OCR, route it through Claude vision separately.

Usage:
  python ingest_agenda.py                  # all agendas in sources.json
  python ingest_agenda.py --date 2026-06-15
Reads PG_* + ANTHROPIC_API_KEY from env. Needs tesseract-ocr installed.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import urllib.parse
from pathlib import Path

import anthropic
import fitz  # pymupdf
import psycopg2
import psycopg2.extras
import pytesseract
import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"
RAW_DIR = HERE / "data" / "pdfs"
STRUCT_MODEL = os.getenv("CC_AGENDA_MODEL", "claude-haiku-4-5")

ITEM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "label": {"type": "string"},
            "title": {"type": "string"},
            "item_type": {"type": "string", "enum": ["SECTION", "ITEM"]},
        },
        "required": ["label", "title", "item_type"]}}},
    "required": ["items"],
}

STRUCT_SYSTEM = """You are given the raw OCR text of a scanned county Board of \
Commissioners agenda. Extract the agenda structure exactly as printed: section \
headers (e.g. Consent Agenda, Public Comment, New Business) as SECTION, and the \
individual numbered or bulleted business items as ITEM. Use the printed label \
if present (e.g. "5a", "1."), else "". Do NOT include the masthead (commissioner \
roster, address) or page furniture. Do not invent items not in the text."""


def _connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"], port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "postgres"), user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"], sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=20)


def _download(base: str, path: str, dest: Path) -> bool:
    url = base.rstrip("/") + "/" + urllib.parse.quote(path)
    r = requests.get(url, timeout=40)
    if r.status_code != 200 or not r.content:
        return False
    dest.write_bytes(r.content)
    return True


def _ocr(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    out = []
    for page in doc:
        # if the page already has embedded text, use it; else OCR the raster
        native = page.get_text().strip()
        if len(native) > 40:
            out.append(native)
        else:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img))
    return "\n".join(out)


def _structure(text: str, client) -> list[dict]:
    msg = client.messages.create(
        model=STRUCT_MODEL, max_tokens=4000,
        system=STRUCT_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": ITEM_SCHEMA}},
        messages=[{"role": "user", "content": f"OCR text of the agenda:\n\n{text}"}],
    )
    return json.loads(next(b.text for b in msg.content if b.type == "text"))["items"]


def ingest_one(entry: dict, src: dict, conn, client) -> str:
    date = entry["meeting_date"]
    meeting_id = f"SURRY_{date.replace('-', '_')}"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf = RAW_DIR / f"{meeting_id}.pdf"
    if not pdf.exists():
        if not _download(src["base_url"], entry["path"], pdf):
            return f"{meeting_id}: DOWNLOAD FAILED"
    text = _ocr(pdf)
    if len(text.strip()) < 60:
        return f"{meeting_id}: OCR EMPTY (poor scan; consider vision fallback)"
    items = _structure(text, client)

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO m1_agenda.meetings (meeting_id, source_id, jurisdiction, meeting_type, meeting_date)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (meeting_id) DO UPDATE SET meeting_date=EXCLUDED.meeting_date;
    """, (meeting_id, entry["path"], src.get("jurisdiction", "Surry County"),
          src.get("meeting_type", "Board of Commissioners"), date))
    cur.execute("DELETE FROM m1_agenda.items WHERE meeting_id=%s", (meeting_id,))
    rows = [(f"{meeting_id}_{i}", meeting_id, i, it["label"], it["title"], it["item_type"], it["title"])
            for i, it in enumerate(items)]
    psycopg2.extras.execute_values(cur,
        "INSERT INTO m1_agenda.items (item_id, meeting_id, ordinal, label, title, item_type, content) VALUES %s",
        rows)
    conn.commit(); cur.close()
    return f"{meeting_id}: {len(items)} items"


def main() -> int:
    ap = argparse.ArgumentParser(description="Surry agenda ingester (OCR path)")
    ap.add_argument("--date", help="ingest a single meeting_date (YYYY-MM-DD)")
    args = ap.parse_args()
    src = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = src["agendas"]
    if args.date:
        entries = [e for e in entries if e["meeting_date"] == args.date]
    conn = _connect(); client = anthropic.Anthropic()
    for e in entries:
        try:
            print(ingest_one(e, src, conn, client), flush=True)
        except Exception as exc:
            print(f"{e['meeting_date']}: ERROR {type(exc).__name__}: {str(exc)[:160]}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
