"""Fetch the daily Open-Meteo forecast for Chicago and load it into DuckDB.

Writes data/raw/weather_daily.csv and replaces the table raw.forecast.
"""

import csv
from pathlib import Path

import duckdb
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "raw" / "weather_daily.csv"
DB_PATH = PROJECT_ROOT / "morning_brief.duckdb"

# past_days=6 adds the previous 6 days, so the weather covers the same
# 7-day window as the 311 data (plus the next 6 forecast days).
ENDPOINT = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=41.8781&longitude=-87.6298"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
    "&timezone=America%2FChicago"
    "&past_days=6"
)

FIELDS = ["date", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "weather_code"]


def fetch_forecast():
    """Call Open-Meteo and turn its column arrays into one dict per day."""
    response = requests.get(ENDPOINT, timeout=60)
    response.raise_for_status()
    daily = response.json()["daily"]
    rows = []
    for i, day in enumerate(daily["time"]):
        rows.append({
            "date": day,
            "temperature_2m_max": daily["temperature_2m_max"][i],
            "temperature_2m_min": daily["temperature_2m_min"][i],
            "precipitation_sum": daily["precipitation_sum"][i],
            "weather_code": daily["weather_code"][i],
        })
    return rows


def write_csv(rows):
    """Write the daily rows to the raw CSV."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def load_duckdb():
    """Replace raw.forecast with the contents of the CSV (all columns as text)."""
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        "CREATE OR REPLACE TABLE raw.forecast AS "
        "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
        [str(CSV_PATH)],
    )
    count = con.execute("SELECT count(*) FROM raw.forecast").fetchone()[0]
    con.close()
    return count


def main():
    print("Fetching Open-Meteo daily weather for Chicago ...")
    rows = fetch_forecast()
    write_csv(rows)
    count = load_duckdb()
    print(f"Loaded {count} rows into raw.forecast")


if __name__ == "__main__":
    main()
