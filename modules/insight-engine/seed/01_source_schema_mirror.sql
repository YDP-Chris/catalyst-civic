-- Catalyst Civic — LOCAL source-schema mirror (for testing the insight engine)
--
-- This recreates the *upstream* source tables the insight engine reads, as
-- mapped from the push scripts. It is NOT Simon's production schema and is not
-- part of the pipelines — it is a local dev fixture so the read layer can be
-- exercised without access to the live database. Only the columns the lenses
-- actually read are included; production tables have more.
--
-- The m1_insights schema (insights, reports) is created by the engine itself
-- (modules/insight-engine/src/insight_engine/schema.py) — do not create it here.
--
-- Load order: this file first, then 02_seed_elkin.sql.

CREATE SCHEMA IF NOT EXISTS m1_agenda;
CREATE SCHEMA IF NOT EXISTS m1_transcript;
CREATE SCHEMA IF NOT EXISTS m1_minutes;
CREATE SCHEMA IF NOT EXISTS cco;

-- --- Agenda lane -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS m1_agenda.meetings (
    meeting_id    TEXT PRIMARY KEY,
    source_id     TEXT,
    jurisdiction  TEXT,
    meeting_type  TEXT,
    meeting_date  DATE,
    location      TEXT,
    metadata      JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS m1_agenda.items (
    item_id       TEXT PRIMARY KEY,
    meeting_id    TEXT REFERENCES m1_agenda.meetings(meeting_id),
    ordinal       INTEGER,
    label         TEXT,
    title         TEXT,
    item_type     TEXT,
    source_page   INTEGER,
    content       TEXT,
    item_text     TEXT,
    metadata      JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- --- Transcript lane -------------------------------------------------------
CREATE TABLE IF NOT EXISTS m1_transcript.meetings (
    meeting_id        TEXT PRIMARY KEY,
    source_id         TEXT,
    jurisdiction      TEXT,
    meeting_date      DATE,
    disposition_code  TEXT,
    pass_95_gate      BOOLEAN,
    total_turns       INTEGER,
    metadata          JSONB DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS m1_transcript.turns (
    turn_row_id   BIGSERIAL PRIMARY KEY,
    meeting_id    TEXT REFERENCES m1_transcript.meetings(meeting_id),
    turn_id       TEXT,
    ordinal       INTEGER,
    phase         TEXT,
    speaker_role  TEXT,
    speaker_name  TEXT,
    content       TEXT,
    metadata      JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- --- Minutes lane ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS m1_minutes.meetings (
    meeting_id    TEXT PRIMARY KEY,
    source_id     TEXT,
    jurisdiction  TEXT,
    meeting_type  TEXT,
    meeting_date  DATE,
    is_complete   BOOLEAN,
    metadata      JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS m1_minutes.excerpts (
    excerpt_id    TEXT PRIMARY KEY,
    meeting_id    TEXT REFERENCES m1_minutes.meetings(meeting_id),
    ordinal       INTEGER,
    content       TEXT,
    metadata      JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- --- Authority layer (Civic Change Ontology) -------------------------------
CREATE TABLE IF NOT EXISTS cco.registry (
    registry_id    TEXT PRIMARY KEY,
    category       TEXT,
    canonical_name TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cco.identities (
    registry_id  TEXT REFERENCES cco.registry(registry_id),
    alias_name   TEXT,
    source_id    TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (registry_id, alias_name)
);

CREATE TABLE IF NOT EXISTS cco.observations (
    fact_id        BIGSERIAL PRIMARY KEY,
    registry_id    TEXT REFERENCES cco.registry(registry_id),
    fact_key       TEXT,
    fact_value     JSONB DEFAULT '{}'::jsonb,
    source_id      TEXT,
    evidence       TEXT,
    effective_date DATE,
    created_at     TIMESTAMPTZ DEFAULT now()
);
