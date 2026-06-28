#!/usr/bin/env python
"""
Content Engine Self-Harness — smoke loop.

Compares a CANDIDATE report-writer prompt against the FROZEN baseline, scored by
the LOCKED judge over frozen fixtures. Reports the in-sample and held-out deltas
and a promote / hold recommendation. Nothing is promoted automatically — this
prints the recipe; a human (or the pulse digest) decides.

The discipline that makes this a Self-Harness and not just an eval:
  - the judge (judge.py) is locked; you optimize the prompt, never the judge
  - fixtures are frozen and split in-sample / held-out
  - a candidate is promotable only if it gains in-sample WITHOUT regressing
    held-out (held-out guards against overfitting the prompt to the fixtures)

Usage:
  python smoke.py                          # baseline vs active.json (or candidate)
  python smoke.py --candidate prompts/candidate.json
  python smoke.py --runs 1                 # samples per fixture (default 1)

Requires ANTHROPIC_API_KEY. Generation + judging both call Claude, so this costs
tokens; keep fixture sets small.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS_DIR.parent / "src"))

from content_engine.reporter import render_markdown  # noqa: E402
from judge import score_report, RUBRIC_VERSION  # noqa: E402

FIXTURES = HARNESS_DIR / "fixtures" / "synthetic.json"
BASELINE = HARNESS_DIR / "prompts" / "baseline.json"


def _load_prompt(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["system"], data["instruction"]


def _score_set(fixture_sets: list[dict], system: str, instruction: str, runs: int) -> float:
    """Mean judge total across every fixture in a split (averaged over runs)."""
    totals = []
    for fx in fixture_sets:
        insights = fx["insights"]
        for _ in range(runs):
            md = render_markdown(insights, system_prompt=system, report_instruction=instruction)
            verdict = score_report(md, insights)
            totals.append(verdict["total"])
            print(f"    [{fx['name']}] total={verdict['total']} "
                  f"ground={verdict['groundedness']} cite={verdict['citation']} "
                  f"unsupported={len(verdict['unsupported_claims'])} "
                  f"style_violations={verdict['style_violations']}")
    return sum(totals) / len(totals) if totals else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Engine Self-Harness smoke loop")
    parser.add_argument("--candidate", help="Path to candidate prompt json (default: prompts/active.json)")
    parser.add_argument("--runs", type=int, default=1, help="Samples per fixture")
    args = parser.parse_args()

    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    in_sample = fixtures["in_sample"]
    held_out = fixtures["held_out"]

    base_sys, base_inst = _load_prompt(BASELINE)
    cand_path = Path(args.candidate) if args.candidate else (HARNESS_DIR / "prompts" / "active.json")
    if not cand_path.exists():
        print(f"No candidate at {cand_path}. Create one (copy baseline.json) and edit its prompt.")
        return 1
    cand_sys, cand_inst = _load_prompt(cand_path)

    print(f"Judge: {RUBRIC_VERSION} | candidate: {cand_path.name}\n")

    print("Baseline / in-sample:")
    base_in = _score_set(in_sample, base_sys, base_inst, args.runs)
    print("Candidate / in-sample:")
    cand_in = _score_set(in_sample, cand_sys, cand_inst, args.runs)
    print("Baseline / held-out:")
    base_ho = _score_set(held_out, base_sys, base_inst, args.runs)
    print("Candidate / held-out:")
    cand_ho = _score_set(held_out, cand_sys, cand_inst, args.runs)

    d_in = cand_in - base_in
    d_ho = cand_ho - base_ho
    print("\n=== Self-Harness result ===")
    print(f"in-sample : baseline {base_in:.1f} -> candidate {cand_in:.1f}  (Δ_in = {d_in:+.1f})")
    print(f"held-out  : baseline {base_ho:.1f} -> candidate {cand_ho:.1f}  (Δ_ho = {d_ho:+.1f})")

    if d_in > 0 and d_ho >= 0:
        print("RECOMMENDATION: PROMOTE — gains in-sample, no held-out regression.")
        print("  Recipe: cp the candidate to prompts/active.json (production loads active with safe fallback).")
    else:
        print("RECOMMENDATION: HOLD — either no in-sample gain or a held-out regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
