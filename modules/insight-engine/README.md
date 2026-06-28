# Insight Engine

A read-only analytical layer over the Catalyst Civic database. It runs a set of
**lenses** against the civic corpus, produces structured, evidence-backed
**insights**, and writes them into a new `m1_insights` Postgres schema.

This is the missing read side of the platform: the pipelines are write-oriented
(intake, parse, push), and the engine turns that structured record into findings
a researcher can act on. Every insight links back to the source record
(`meeting_id` / `item_id` / `turn_row_id` / `fact_id`) so any claim can be walked
straight back to the public document it came from.

## Lenses

| Lens | Question | Reads |
|---|---|---|
| `influence` | Who keeps showing up across the record? | `cco.registry`, `cco.observations`, `cco.identities` |
| `spending` | Where is the money moving? | `m1_agenda.items` + `m1_agenda.meetings` |
| `topics` | What does the council keep coming back to? | `m1_agenda.items` + `m1_agenda.meetings` |
| `votes` | Where did the decisions get made? | `m1_transcript.turns` + `m1_transcript.meetings` |

`influence` is the deepest lens (the authority layer is the richest cross-cutting
signal). `spending` / `topics` / `votes` are v0.1 baselines with the same
interface, designed to be deepened in place.

## Run

```bash
cd modules/insight-engine

# one-time: create the m1_insights schema
python3 scripts/run_insight_engine.py --init-schema --dry-run

# analyze and write insights
python3 scripts/run_insight_engine.py

# preview without writing
python3 scripts/run_insight_engine.py --dry-run

# a single lens
python3 scripts/run_insight_engine.py --lens influence
python3 scripts/run_insight_engine.py --list-lenses
```

Reads the standard `PG_*` env vars (same as the push scripts). The engine opens
a read-only connection; it never writes to the source schemas.

## Output: `m1_insights.insights`

| Column | Meaning |
|---|---|
| `insight_id` / `dedupe_key` | stable id; re-runs upsert instead of duplicating |
| `lens`, `title`, `summary` | the finding |
| `severity`, `confidence` | `info` / `notable` / `high`; 0-1 confidence |
| `entity_refs` | `cco.registry_id`s involved (jsonb) |
| `metrics` | the computed numbers (jsonb) |
| `evidence` | source-traceable pointers (jsonb) |

## Adding a lens

1. Subclass `Lens` in `src/insight_engine/lenses/`.
2. Implement `analyze(cur) -> list[Insight]` (read-only).
3. Register it in `src/insight_engine/registry.py`.

The runner and CLI pick it up automatically.

## Next steps

- Deepen `spending` with department-report figures and minutes reconciliation.
- `topics`: move from a fixed lexicon to term-frequency / embeddings.
- `votes`: per-item pass/fail/tabled tracking and split-vote detection.
- See `modules/content-engine` for the report layer that consumes these insights.
