# Content Engine

Turns the Insight Engine's evidence-backed findings into written **reports**, and
writes them back into `m1_insights.reports`.

It reads insights from `m1_insights.insights`, hands them to Claude under a strict
groundedness contract, and stores the resulting Markdown report. The contract is
the important part: these reports concern real local officials and real public
decisions, so the model is instructed to use **only** the supplied insights and
evidence, cite the source record for every claim, and flag thin data rather than
overstate it.

## Run

```bash
cd modules/content-engine

# write a report from all current insights
python3 scripts/run_content_engine.py

# one lens / high-severity only
python3 scripts/run_content_engine.py --lens spending
python3 scripts/run_content_engine.py --severity high

# preview without writing to the DB
python3 scripts/run_content_engine.py --dry-run

# tag the intended audience (general | legal | press)
python3 scripts/run_content_engine.py --audience legal
```

Requires `ANTHROPIC_API_KEY` and the `PG_*` env vars.

## Model

Defaults to `claude-opus-4-8` with adaptive thinking and streaming. Override with
`CC_REPORT_MODEL` (e.g. `claude-sonnet-4-6` for cheaper batch runs) and
`CC_REPORT_MAX_TOKENS`.

## Output: `m1_insights.reports`

| Column | Meaning |
|---|---|
| `report_id` | stable id; re-runs upsert |
| `title`, `body_md` | the report (GitHub-flavored Markdown) |
| `audience` | `general` / `legal` / `press` |
| `insight_refs` | the `insight_id`s the report was built from (jsonb) |
| `status` | `draft` by default — a human/quality gate promotes from here |
| `model`, `generated_at` | provenance |

Reports land as `draft`. Nothing about real officials should auto-publish; a
review gate (see the Self-Harness plan in `harness/README.md`) decides what ships.

## Full pipeline

Run both stages together via the conductor:

```bash
python3 ../../pipelines/mode-1-meetings/insights/conductor.py --init-schema
```
