#!/usr/bin/env bash
# Run the full Chicago Morning Brief pipeline: ingest, dbt run and test,
# append new complete days to the history CSVs, then render brief.md.
# Run from the project root with your virtual environment activated.
set -euo pipefail

cd "$(dirname "$0")"

echo "== Ingesting 311 requests =="
python ingest/ingest_311.py

echo "== Ingesting weather =="
python ingest/ingest_weather.py

echo "== dbt run =="
dbt run --profiles-dir .

echo "== dbt test =="
dbt test --profiles-dir .

# set -e above stops the script if dbt fails, so history is never appended
# and no brief is rendered from stale data.
echo "== Appending history =="
python scripts/append_history.py

echo "== Rendering brief.md =="
python scripts/render_brief.py
