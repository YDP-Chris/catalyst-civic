# Local test seed — Elkin, NC

A self-contained way to exercise the insight engine without access to the live
Catalyst Civic database. It mirrors the **upstream source schema** the engine
reads (`m1_agenda`, `m1_transcript`, `cco`) and seeds it with a synthetic
**Town of Elkin** (Surry County, NC) dataset.

## What's real and what isn't

- **Real:** Elkin's geography and issue areas — Big Elkin Creek, the Municipal
  Park, Main Street / downtown revitalization, the water treatment plant, sewer
  capacity, Yadkin Valley tourism.
- **Fictional:** the council members, the developer (`Crater Ridge Development
  LLC`), all dollar figures, and all quotes.

This is a test fixture, not a record of real Elkin proceedings. It exists so the
read layer and the four lenses produce meaningful output on demand. It does not
fabricate the actions of real officials.

## Files

| File | Purpose |
|---|---|
| `01_source_schema_mirror.sql` | recreates the upstream tables the lenses read (columns used by the engine only) |
| `02_seed_elkin.sql` | the Elkin dataset, sized to clear the lenses' default thresholds |
| `load_local.sh` | createdb + load both SQL files + run the engine + print a sample |

## Run it (needs a Postgres SERVER)

```bash
export PG_HOST=localhost PG_PORT=5432 PG_DB=catalyst_civic PG_USER=postgres PG_PASS=postgres
bash modules/insight-engine/seed/load_local.sh
```

Then generate a report:

```bash
python3 modules/content-engine/scripts/run_content_engine.py --dry-run
```

## What it should produce

- **influence** — `Crater Ridge Development LLC` (6 records) and `Elkin Planning
  Board` (5 records) surface; below-threshold entities (Commissioner Whitaker,
  Yadkin Valley Wine Trail) do not, at default settings.
- **spending** — the $2.4M water plant upgrade as `high`; fire pumper, paving,
  greenway match, park restroom as notable.
- **topics** — `Water & sewer` across 8 meetings; downtown/development threads.
- **votes** — the 2024-09-09 session flagged for motion/vote density.

## Notes

- The mirror is a **local dev convenience**, not part of Simon's production
  schema. Keep it out of any upstream PR's production path (it lives under the
  module's `seed/` and is only invoked explicitly).
- To clear thresholds with a smaller seed, lower them via env (e.g.
  `CC_INFLUENCE_MIN_RECORDS=3`, `CC_TOPICS_MIN_MEETINGS=3`).
- Replace this with a real frozen sample (a `pg_dump` of a small slice of the
  live DB) once one is available — keep this synthetic seed so the engine stays
  runnable offline.
