# Surry County transcript ingester

Pulls real public meeting transcripts for the Surry County (NC) Board of
Commissioners from their [YouTube channel](https://www.youtube.com/@surrycountynccommissioners)
and turns them into structured, ontology-tagged civic records our insight engine
can read. This is our own intake path for validating the engine on real local
data, parallel to Simon's agenda-PDF + PRATTLE pipelines.

## Pipeline (Palantir-style: objects + links + provenance)

```
[1 fetch]      YouTube auto-transcript  ->  data/raw/<vid>.json   (DONE, runnable now)
                  raw, speaker-blind, phonetically noisy segments
[2 reconstruct] merge segments into utterances; phonetic-correct
                  proper nouns; segment by Roberts Rules phase     -> m1_transcript.turns
[3 attribute]  assign speaker per turn (presider cues, roster)     -> turns.speaker_name/role
[4 tag]        extract the ONTOLOGY with provenance                -> cco.registry / identities / observations
[5 load]       write to our Postgres (Supabase)
[6 engine]     insight-engine -> m1_insights -> content-engine report
```

Stage 1 is built and runs with no DB. Stages 2-5 are the build ahead.

## The ontology (stage 4 — "robust tagging")

This is the heart of it, and what makes the influence lens and graph-style
discovery work. Model the record as **objects + links + observations**, every one
carrying provenance back to a source span:

- **Objects** (`cco.registry`): Person, Organization, Board/Agency, Parcel/Property,
  Location, Ordinance/Resolution, Topic, Motion/Vote.
- **Aliases** (`cco.identities`): name variants resolved to one object
  ("Commissioner Hyatt" / "Mr. Hyatt" / "Eddie Harris").
- **Observations** (`cco.observations`): atomic facts and links, each with
  `source_id` (video id), a timestamp/turn ref, and the **verbatim evidence span** —
  e.g. `person --moved--> motion`, `org --applicant_on--> rezoning`,
  `parcel --located_at--> address`, `person --voted(aye/nay)--> motion`.

Provenance on every fact is the non-negotiable: it is what lets a researcher
walk any claim back to the exact moment in the public meeting, and what the
content engine's groundedness contract relies on. Extraction is LLM-based
(NER + relation extraction) with the evidence span stored, not just the label.

## Run (stage 1)

```bash
# from repo root, in the project venv
.venv/bin/python modules/ingest-surry/fetch_transcripts.py          # all in sources.json
.venv/bin/python modules/ingest-surry/fetch_transcripts.py --video FRNjggFp0_M
```

Staged output lands in `data/raw/` (gitignored). `sources.json` is the seed list
of real meetings; expand it from the channel's uploads playlist.

## Status

- Stage 1 (fetch) built and validated: 5 real Surry meetings staged
  (2022-2025, ~45k words). The raw stream is messy by design ("ALG Allegiance",
  no speaker labels) — that is the reconstruction problem stages 2-4 solve.
- Needs: our own Postgres (a dedicated Supabase project) + its connection string
  in the shared `.env` as `PG_*`, so the loader + engine run via psycopg2.
- Next build: stage 2 (reconstruct turns) and stage 4 (ontology tagger).
