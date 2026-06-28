#!/usr/bin/env python
"""
Content Engine — turns evidence-backed insights into a written report.

Reads insights from m1_insights.insights, hands them to Claude with a strict
groundedness contract (use only the supplied facts and evidence; cite the
source record for every claim; no fabrication), and writes the resulting
markdown report back into m1_insights.reports.

Groundedness is the whole point: these reports concern real local officials and
public decisions, so an unsupported claim is worse than no claim. The model is
instructed to work only from the insight rows it is given.

Model: defaults to claude-opus-4-8 (override via CC_REPORT_MODEL). Uses adaptive
thinking and streaming, per current Anthropic SDK guidance for long outputs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import anthropic
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: anthropic. Install with `pip install anthropic`."
    ) from exc

# Reuse the insight-engine DB helper so both modules share one connection idiom.
INSIGHT_SRC = Path(__file__).resolve().parents[3] / "insight-engine" / "src"
sys.path.insert(0, str(INSIGHT_SRC))
from common.db import cursor  # noqa: E402

ENGINE_VERSION = "content.engine.v0.1"
MODEL = os.getenv("CC_REPORT_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.getenv("CC_REPORT_MAX_TOKENS", "16000"))

SYSTEM_PROMPT = """You are a civic-records analyst writing for a local-government \
transparency platform. Your readers are journalists, attorneys, and engaged \
residents who use these reports to navigate years of public records quickly.

Hard rules:
- Use ONLY the insights and evidence provided in the user message. Do not add \
facts, names, figures, or conclusions that are not supported by that data.
- Every substantive claim must be traceable to the evidence given. Reference the \
meeting or record it came from (by meeting id or date) so a reader can verify it.
- If the data is thin or ambiguous, say so plainly rather than overstating.
- Neutral, factual tone. No partisan framing, no speculation about motive.
- Plain professional prose. No emojis. Use regular hyphens, never em dashes or \
en dashes. Avoid hype.
- Output GitHub-flavored Markdown: a title, a short summary, then sections.
"""

REPORT_INSTRUCTION = """Write a civic intelligence report from the insights below.

Structure:
1. A title (H1).
2. A 2-4 sentence executive summary of what the records show.
3. One section per theme (group related insights). In each, state the finding \
and cite the supporting evidence (meeting id / date / record).
4. A short "How to verify" closing note pointing readers to the source records.

Insights (JSON):
"""


def _fetch_insights(lens: str | None, limit: int, min_severity: str | None) -> list[dict]:
    clauses = []
    params: dict = {"limit": limit}
    if lens:
        clauses.append("lens = %(lens)s")
        params["lens"] = lens
    if min_severity == "high":
        clauses.append("severity = 'high'")
    elif min_severity == "notable":
        clauses.append("severity IN ('notable', 'high')")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT insight_id, lens, title, summary, severity, confidence,
               entity_refs, metrics, evidence
        FROM m1_insights.insights
        {where}
        ORDER BY (severity = 'high') DESC, confidence DESC
        LIMIT %(limit)s;
    """
    with cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _load_active_prompt() -> tuple[str, str]:
    """
    Return (system_prompt, report_instruction).

    Self-Harness hook: if harness/prompts/active.json exists, load the promoted
    candidate prompt from it; otherwise fall back to the locked in-file defaults.
    The fallback is deliberate — a missing or malformed active prompt must never
    take the report writer down.
    """
    active = Path(__file__).resolve().parents[2] / "harness" / "prompts" / "active.json"
    try:
        if active.exists():
            data = json.loads(active.read_text(encoding="utf-8"))
            system = data.get("system") or SYSTEM_PROMPT
            instruction = data.get("instruction") or REPORT_INSTRUCTION
            return system, instruction
    except Exception:
        pass
    return SYSTEM_PROMPT, REPORT_INSTRUCTION


def render_markdown(
    insights: list[dict],
    system_prompt: str | None = None,
    report_instruction: str | None = None,
) -> str:
    """
    Generate a report's Markdown from insights. Public so the Self-Harness can
    drive it with explicit candidate prompts; production passes nothing and gets
    the active (or default) prompt.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    if system_prompt is None or report_instruction is None:
        active_system, active_instruction = _load_active_prompt()
        system_prompt = system_prompt or active_system
        report_instruction = report_instruction or active_instruction
    payload = report_instruction + json.dumps(insights, indent=2, default=str)

    # Stream the long report body; collect the final message.
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": payload}],
    ) as stream:
        message = stream.get_final_message()

    return "".join(b.text for b in message.content if b.type == "text").strip()


def _store_report(title: str, body_md: str, insight_ids: list[str], audience: str) -> str:
    # Derive a stable-ish id from the title + first insight, lowercased/sliced.
    import hashlib

    basis = (title + (insight_ids[0] if insight_ids else "")).encode("utf-8")
    report_id = "REP_" + hashlib.sha256(basis).hexdigest()[:16]
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO m1_insights.reports
                (report_id, title, body_md, audience, insight_refs, status,
                 model, engine_version)
            VALUES
                (%(report_id)s, %(title)s, %(body_md)s, %(audience)s,
                 %(insight_refs)s, 'draft', %(model)s, %(engine_version)s)
            ON CONFLICT (report_id) DO UPDATE SET
                title = EXCLUDED.title,
                body_md = EXCLUDED.body_md,
                insight_refs = EXCLUDED.insight_refs,
                model = EXCLUDED.model,
                generated_at = now();
            """,
            {
                "report_id": report_id,
                "title": title,
                "body_md": body_md,
                "audience": audience,
                "insight_refs": json.dumps(insight_ids),
                "model": MODEL,
                "engine_version": ENGINE_VERSION,
            },
        )
    return report_id


def _extract_title(body_md: str, fallback: str) -> str:
    for line in body_md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def generate_report(
    lens: str | None = None,
    limit: int = 40,
    min_severity: str | None = "notable",
    audience: str = "general",
    dry_run: bool = False,
) -> dict:
    """Fetch insights, write a report, persist it. Returns a small result dict."""
    insights = _fetch_insights(lens, limit, min_severity)
    if not insights:
        return {"status": "no_insights", "count": 0}

    body_md = render_markdown(insights)
    title = _extract_title(body_md, fallback=f"Civic Intelligence Report ({lens or 'all lenses'})")
    insight_ids = [i["insight_id"] for i in insights]

    if dry_run:
        return {
            "status": "dry_run",
            "count": len(insights),
            "title": title,
            "body_md": body_md,
        }

    report_id = _store_report(title, body_md, insight_ids, audience)
    return {
        "status": "written",
        "report_id": report_id,
        "title": title,
        "insight_count": len(insights),
    }
