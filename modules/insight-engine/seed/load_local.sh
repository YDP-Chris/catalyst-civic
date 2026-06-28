#!/usr/bin/env bash
# Catalyst Civic — load the local test DB (schema mirror + Elkin seed) and run
# the insight engine end to end. Requires a reachable PostgreSQL SERVER and the
# standard PG_* env vars (PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS).
#
# This is the one-command validation path for any real Postgres: your Pi (with
# the postgresql server package, not just the client), a Supabase connection,
# or Simon's box. It is intentionally idempotent — safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-catalyst_civic}"
PG_USER="${PG_USER:-postgres}"
export PGPASSWORD="${PG_PASS:-postgres}"

PSQL="psql -h $PG_HOST -p $PG_PORT -U $PG_USER"

echo "==> ensuring database $PG_DB exists"
if ! $PSQL -lqt | cut -d '|' -f1 | grep -qw "$PG_DB"; then
  createdb -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DB"
fi

echo "==> loading source-schema mirror"
$PSQL -d "$PG_DB" -v ON_ERROR_STOP=1 -f "$HERE/01_source_schema_mirror.sql"

echo "==> loading Elkin seed"
$PSQL -d "$PG_DB" -v ON_ERROR_STOP=1 -f "$HERE/02_seed_elkin.sql"

echo "==> creating m1_insights schema + running the insight engine"
python3 "$HERE/../scripts/run_insight_engine.py" --init-schema

echo "==> insights written. Sample:"
$PSQL -d "$PG_DB" -c \
  "SELECT lens, severity, left(title,60) AS title FROM m1_insights.insights ORDER BY lens, severity DESC LIMIT 20;"

echo
echo "Done. Next: write a report with"
echo "  python3 $HERE/../../content-engine/scripts/run_content_engine.py --dry-run"
