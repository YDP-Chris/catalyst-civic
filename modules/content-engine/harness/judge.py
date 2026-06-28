#!/usr/bin/env python
"""
LOCKED judge for the Content Engine Self-Harness.

This rubric is the fixed target the report-writer prompt is optimized against.
DO NOT tune it to make candidate prompts look better — that defeats the whole
loop. A locked judge is what lets the generator improve against a stable bar
instead of a moving one. If the rubric genuinely needs to change, bump
RUBRIC_VERSION and re-baseline every fixture from scratch.

The judge scores one report against the exact insights it was generated from.
Groundedness is weighted highest: in a civic-transparency product, a fabricated
or untraceable claim about a real official is the worst possible failure.

Scoring axes (0-25 each, 100 total):
  groundedness  — every claim supported by the supplied evidence; zero fabrication
  citation      — claims reference the source record (meeting id / date)
  neutrality    — factual, non-partisan, no speculation about motive
  structure     — title, summary, themed sections, a verify note; clean Markdown
Style gate (hard): emojis or em/en dashes cap the total at 70 regardless of axes.
"""
from __future__ import annotations

import json
import os
import re

try:
    import anthropic
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: anthropic. `pip install anthropic`.") from exc

RUBRIC_VERSION = "civic-report-judge.v1"
JUDGE_MODEL = os.getenv("CC_JUDGE_MODEL", "claude-opus-4-8")

# Hard style gate: these must never appear in civic/brand-grade copy.
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]"
)
_LONG_DASH_RE = re.compile("[–—]")  # en dash, em dash

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "groundedness": {"type": "integer"},
        "citation": {"type": "integer"},
        "neutrality": {"type": "integer"},
        "structure": {"type": "integer"},
        "unsupported_claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim claims NOT supported by the supplied insights.",
        },
        "notes": {"type": "string"},
    },
    "required": ["groundedness", "citation", "neutrality", "structure",
                 "unsupported_claims", "notes"],
    "additionalProperties": False,
}

JUDGE_SYSTEM = f"""You are a LOCKED evaluator ({RUBRIC_VERSION}) for civic \
intelligence reports. You score a report strictly against the insights it was \
generated from. You are adversarial about groundedness: hunt for any claim, \
name, number, or conclusion in the report that is not supported by the supplied \
insights/evidence, and list each one verbatim under unsupported_claims.

Score each axis 0-25:
- groundedness: 25 only if every claim is supported by the supplied evidence and \
nothing is invented. Subtract heavily for each unsupported claim.
- citation: are claims tied to their source record (meeting id or date)?
- neutrality: factual and non-partisan; no speculation about motive or intent.
- structure: title, executive summary, themed sections, a verification note, \
clean Markdown.

Return ONLY the structured score object. Do not rewrite the report."""


def _style_violations(report_md: str) -> int:
    return len(_EMOJI_RE.findall(report_md)) + len(_LONG_DASH_RE.findall(report_md))


def score_report(report_md: str, insights: list[dict]) -> dict:
    """Judge one report against its source insights. Returns a score dict."""
    client = anthropic.Anthropic()
    user = (
        "INSIGHTS THE REPORT MUST BE GROUNDED IN (JSON):\n"
        + json.dumps(insights, indent=2, default=str)
        + "\n\nREPORT TO EVALUATE (Markdown):\n"
        + report_md
    )
    msg = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=JUDGE_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCORE_SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )
    raw = next(b.text for b in msg.content if b.type == "text")
    result = json.loads(raw)

    axes = ("groundedness", "citation", "neutrality", "structure")
    total = sum(int(result.get(a, 0)) for a in axes)

    violations = _style_violations(report_md)
    if violations:
        total = min(total, 70)  # hard style gate
    result["style_violations"] = violations
    result["total"] = total
    result["rubric_version"] = RUBRIC_VERSION
    return result
