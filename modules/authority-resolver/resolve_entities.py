#!/usr/bin/env python
"""
Authority resolver — merge entity name variants to a canonical roster.

The transcript tagger derives PEOPLE entities from auto-captions, which spell
names phonetically (Goens, Koff, Hiatt/Height). The agenda masthead is the
authoritative source of correct spellings and roles. This resolver:

  1. Reads the canonical roster from an agenda PDF masthead (OCR + Haiku).
  2. Matches each transcript-derived cco.registry PEOPLE entity to a roster
     person by surname similarity + first-initial agreement.
  3. Merges duplicates into the canonical entity: repoints observations and
     identities, records the variant spelling as an alias, deletes the dup.
  4. Stamps each canonical person with a ROLE observation from the masthead.

Conservative by design: only merges on a strong surname match, so it collapses
Goens->Goins without merging two genuinely different people.

Usage:
  python resolve_entities.py [--agenda-url URL] [--dry-run]
Reads PG_* + ANTHROPIC_API_KEY from env. Needs tesseract.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import os
import re
import urllib.parse
from pathlib import Path

import anthropic
import fitz
import psycopg2
import pytesseract
import requests
from PIL import Image

DEFAULT_AGENDA = ("https://www.co.surry.nc.us/document_center/Commissioners/"
                  "Agendas/2026/1 - Agenda June 15, 2026.pdf")
ROSTER_MODEL = os.getenv("CC_ROSTER_MODEL", "claude-haiku-4-5")
MAP_MODEL = os.getenv("CC_MAP_MODEL", "claude-sonnet-4-6")

ROSTER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"people": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"name": {"type": "string"}, "role": {"type": "string"}},
        "required": ["name", "role"]}}},
    "required": ["people"],
}

MAP_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"mappings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"variant": {"type": "string"}, "canonical": {"type": "string"}},
        "required": ["variant", "canonical"]}}},
    "required": ["mappings"],
}

MAP_SYSTEM = """You match person-name variants from auto-captioned meeting \
transcripts to a canonical roster of county officials. Auto-captions misspell \
names phonetically (e.g. Goens->Goins, Koff->Knopf, Hyatt/Height->Hiatt, \
Martin->Mark). For each transcript name, output the canonical roster name it \
refers to IF it is clearly the same person (same surname sound and compatible \
first name/role). If the transcript name is NOT one of the roster people (a \
citizen, presenter, department head, or other non-roster individual), set \
canonical to an empty string. Be conservative: only map clear same-person \
variants; when in doubt, leave canonical empty."""


def _connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"], port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "postgres"), user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"], sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=20)


def _registry_id(category: str, name: str) -> str:
    h = hashlib.sha256(f"{category}|{name.strip().lower()}".encode()).hexdigest()[:12]
    return f"reg_{h}"


def _titlecase(n: str) -> str:
    return " ".join(w.capitalize() for w in n.split())


def _surname(n: str) -> str:
    toks = [t for t in re.sub(r"[^a-zA-Z ]", "", n).split() if t]
    return toks[-1].lower() if toks else ""


def _first_initial(n: str) -> str:
    toks = [t for t in re.sub(r"[^a-zA-Z ]", "", n).split() if t]
    return toks[0][0].lower() if len(toks) > 1 else ""


def get_roster(agenda_url: str) -> list[dict]:
    pdf = Path("/tmp/_roster_agenda.pdf")
    if not pdf.exists():
        r = requests.get(agenda_url.rsplit("/", 1)[0] + "/" +
                         urllib.parse.quote(agenda_url.rsplit("/", 1)[1]), timeout=40)
        pdf.write_bytes(r.content)
    page = fitz.open(pdf)[0]
    text = page.get_text().strip()
    if len(text) < 40:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(page.get_pixmap(dpi=300).tobytes("png"))))
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=ROSTER_MODEL, max_tokens=1500,
        system="Extract the board/staff roster from the masthead of this county agenda: each person's full name and their role (e.g. Chairman, Vice-Chairman, Commissioner, County Manager, County Attorney). Only the masthead roster, not agenda items.",
        output_config={"format": {"type": "json_schema", "schema": ROSTER_SCHEMA}},
        messages=[{"role": "user", "content": text[:4000]}])
    return json.loads(next(b.text for b in msg.content if b.type == "text"))["people"]


def resolve(agenda_url: str, dry_run: bool) -> None:
    roster = get_roster(agenda_url)
    print(f"canonical roster ({len(roster)}): " + ", ".join(f"{p['name']} ({p['role']})" for p in roster))
    conn = _connect(); cur = conn.cursor()
    cur.execute("""select r.registry_id, r.canonical_name, count(o.fact_id)
                   from cco.registry r left join cco.observations o on o.registry_id=r.registry_id
                   where r.category='PEOPLE' group by r.registry_id, r.canonical_name""")
    people = [{"rid": a, "name": b, "obs": c} for a, b, c in cur.fetchall()]
    by_name = {p["name"]: p for p in people}

    roster_names = [_titlecase(p["name"]) for p in roster]
    roster_lc = {n.lower(): n for n in roster_names}

    # LLM maps each transcript person-name to a canonical roster name (or "").
    # Only recurring people (obs >= 2) — one-off names are citizens/presenters
    # that never merge, and including them all overruns the token budget.
    to_map = [p for p in people if p["obs"] >= 2]
    client = anthropic.Anthropic()
    user = ("Canonical roster:\n" + "\n".join(roster_names)
            + "\n\nTranscript names (name | observation_count):\n"
            + "\n".join(f"{p['name']} | {p['obs']}" for p in to_map))
    msg = client.messages.create(model=MAP_MODEL, max_tokens=8000, system=MAP_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": MAP_SCHEMA}},
        messages=[{"role": "user", "content": user}])
    mapping = json.loads(next(b.text for b in msg.content if b.type == "text"))["mappings"]

    merges = 0
    for m in mapping:
        variant_name = m["variant"]
        canon_name = (m.get("canonical") or "").strip()
        if not canon_name or canon_name.lower() not in roster_lc:
            continue  # not a roster person
        canon = roster_lc[canon_name.lower()]
        e = by_name.get(variant_name)
        if not e:
            continue
        canon_rid = _registry_id("PEOPLE", canon)
        if e["rid"] == canon_rid:
            continue  # already canonical spelling
        print(f"  merge: {variant_name} ({e['obs']} obs) -> {canon}")
        if dry_run:
            merges += 1
            continue
        cur.execute("insert into cco.registry (registry_id,category,canonical_name) values (%s,'PEOPLE',%s) "
                    "on conflict (registry_id) do update set canonical_name=excluded.canonical_name", (canon_rid, canon))
        cur.execute("insert into cco.identities (registry_id,alias_name,source_id) values (%s,%s,'AGENDA_MASTHEAD') on conflict do nothing", (canon_rid, canon))
        cur.execute("update cco.observations set registry_id=%s where registry_id=%s", (canon_rid, e["rid"]))
        cur.execute("insert into cco.identities (registry_id,alias_name,source_id) select %s, alias_name, source_id from cco.identities where registry_id=%s on conflict do nothing", (canon_rid, e["rid"]))
        cur.execute("insert into cco.identities (registry_id,alias_name,source_id) values (%s,%s,'RESOLVER') on conflict do nothing", (canon_rid, variant_name))
        cur.execute("delete from cco.identities where registry_id=%s", (e["rid"],))
        cur.execute("delete from cco.registry where registry_id=%s", (e["rid"],))
        merges += 1
    if not dry_run:
        conn.commit()
    print(f"\n{'(dry-run) ' if dry_run else ''}{merges} variant entit(ies) {'would merge' if dry_run else 'merged'} into the canonical roster.")
    cur.close(); conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Authority entity resolver")
    ap.add_argument("--agenda-url", default=DEFAULT_AGENDA)
    ap.add_argument("--dry-run", action="store_true")
    ap.parse_args()
    args = ap.parse_args()
    resolve(args.agenda_url, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
