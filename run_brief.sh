#!/usr/bin/env bash
# Run the full Chicago Morning Brief pipeline: ingest, then dbt build and test.
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

echo "== Rendering brief.md =="
python scripts/render_brief.py
