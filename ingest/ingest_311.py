"""Fetch the last 7 days of Chicago 311 service requests and load them into DuckDB.

Writes data/raw/chicago_311_requests.csv and replaces the table raw.requests.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "raw" / "chicago_311_requests.csv"
DB_PATH = PROJECT_ROOT / "morning_brief.duckdb"

ENDPOINT = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
ROW_LIMIT = 50000
DAYS = 7

# The portal calls the ID column "sr_number"; we rename it in the query.
FIELDS = [
    "service_request_number",
    "created_date",
    "closed_date",
    "sr_type",
    "status",
    "ward",
    "community_area",
    "latitude",
    "longitude",
]


def window_start():
    """Midnight (Chicago time) six days ago, so the window is 7 calendar days including today."""
    today = datetime.now(ZoneInfo("America/Chicago")).date()
    return today - timedelta(days=DAYS - 1)


def fetch_requests(start_date):
    """Call the Socrata API for requests created on or after start_date."""
    select = ", ".join(
        "sr_number AS service_request_number" if f == "service_request_number" else f
        for f in FIELDS
    )
    params = {
        "$select": select,
        "$where": f"created_date >= '{start_date.isoformat()}T00:00:00'",
        "$order": "created_date",
        "$limit": ROW_LIMIT,
    }
    response = requests.get(ENDPOINT, params=params, timeout=120)
    response.raise_for_status()
    rows = response.json()
    if len(rows) >= ROW_LIMIT:
        print(f"WARNING: hit the {ROW_LIMIT} row limit; some requests may be missing.")
    return rows


def write_csv(rows):
    """Write rows to the raw CSV, keeping only the fields we care about."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_duckdb():
    """Replace raw.requests with the contents of the CSV (all columns as text)."""
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        "CREATE OR REPLACE TABLE raw.requests AS "
        "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
        [str(CSV_PATH)],
    )
    count = con.execute("SELECT count(*) FROM raw.requests").fetchone()[0]
    con.close()
    return count


def main():
    start = window_start()
    print(f"Fetching 311 requests created since {start} ...")
    rows = fetch_requests(start)
    write_csv(rows)
    count = load_duckdb()
    print(f"Loaded {count} rows into raw.requests")


if __name__ == "__main__":
    main()
