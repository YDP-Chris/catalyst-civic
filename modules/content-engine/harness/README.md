# Content Engine Self-Harness

A Self-Harness loop for the report writer: optimize the generator prompt against
a **locked judge** over **frozen fixtures**, promote only on a measured gain that
doesn't regress held-out. Same pattern as the prior pilots (blog-reviewer,
marketing, winery-scout, apparel-summarize, valleysomm-narrative) — this is the
first one applied to a civic-records generator, and the judge's dominant axis is
**groundedness**: every claim in a report must trace to the supplied evidence,
zero fabrication. In a transparency product about real officials, an untraceable
claim is the worst failure mode, so it's the thing the harness defends.

## Pieces

| File | Role | Locked? |
|---|---|---|
| `judge.py` | groundedness + civic-report rubric scorer (`civic-report-judge.v1`) | LOCKED |
| `fixtures/synthetic.json` | frozen insight sets, split in-sample / held-out | FROZEN |
| `prompts/baseline.json` | the reference report-writer prompt | FROZEN |
| `prompts/active.json` | the promoted prompt production loads (absent = in-file default) | swappable |
| `smoke.py` | baseline vs candidate, scored by the judge, prints Δ + recipe | — |

The thing being optimized is the **report-writer prompt**. `reporter.render_markdown()`
loads `prompts/active.json` with a safe fallback to the in-file default, so a
missing or malformed active prompt never takes the writer down.

## Loop

```bash
cd modules/content-engine/harness

# 1. draft a candidate (start from the frozen baseline)
cp prompts/baseline.json prompts/candidate.json
#    ... edit candidate.json's "system"/"instruction" ...

# 2. smoke it: candidate vs baseline, judged over frozen fixtures
python3 smoke.py --candidate prompts/candidate.json

# 3. promote ONLY if Δ_in > 0 and Δ_ho >= 0
cp prompts/candidate.json prompts/active.json
```

`Δ_in` is the in-sample gain; `Δ_ho` is the held-out gain. Held-out is the
overfitting guard: a prompt that only wins in-sample is memorizing the fixtures,
not improving. Promote on in-sample gain **with no held-out regression**.

## Rules that keep it honest

- **Never tune the judge to flatter a candidate.** If the rubric is wrong, bump
  `RUBRIC_VERSION` in `judge.py` and re-baseline every fixture — don't nudge it.
- **Never edit a fixture in place.** Append new frozen sets; the deltas only mean
  something against a stable corpus.
- **Keep `baseline.json` frozen** so historical deltas stay comparable.

## Rollback

Production reads `prompts/active.json`. To revert a regression, delete `active.json`
(falls back to the in-file default) or `cp prompts/baseline.json prompts/active.json`.
No code change, no redeploy.

## Status / next steps

- Fixtures are **synthetic** until the production DB is reachable. Add real frozen
  insight sets (pulled from `m1_insights.insights`) alongside the synthetic ones;
  do not delete the synthetic set (it keeps the loop runnable offline).
- A scheduled nightly smoke + ntfy pulse digest is the natural follow-on (mirrors
  the Self-Harness Pulse across the other loops). Not wired yet — this is the
  generator + locked judge + fixtures + smoke core.
- A second-order harness on the *judge* itself (Phase 2, as deferred on the
  marketing pilot) is possible later but out of scope here.
