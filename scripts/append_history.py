"""Append new rows from the current model outputs to the committed history CSVs.

Each run replaces raw.requests, so the database only ever holds the last 7 days.
History lives in CSVs under data/history/ so it survives across runs:

- daily_brief_history.csv         one row per date            (from mart_daily_brief)
- daily_type_history.csv          one row per date + sr_type  (from int_311_daily)
- daily_neighborhood_history.csv  one row per date + area     (from int_311_daily_by_area)

Information-only calls are not service requests, so neither the type file nor the
neighborhood file includes them.

Rules:
- Only complete days are appended (dates before today in Chicago time). Today's
  count is partial, and since existing rows are never rewritten, saving it would
  freeze a partial number forever. Each date joins history on the run after it ends.
- Existing rows are never rewritten or deleted, and a row whose key is already in
  the file is never appended again. Running this twice in a row adds nothing.
"""

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "morning_brief.duckdb"
HISTORY_DIR = PROJECT_ROOT / "data" / "history"

INFO_ONLY = "311 INFORMATION ONLY CALL"

# file name, CSV columns, key columns, query (columns in the same order as the CSV)
HISTORY_FILES = [
    (
        "daily_brief_history.csv",
        ["date", "temp_max_f", "temp_min_f", "precipitation_mm", "total_requests",
         "top_request_type", "top_type_count", "open_requests"],
        ["date"],
        """
        select brief_date, temp_max_f, temp_min_f, precipitation_mm, total_requests,
               top_request_type, top_request_type_count, open_requests
        from mart_daily_brief
        where brief_date < ?
        order by brief_date
        """,
    ),
    (
        "daily_type_history.csv",
        ["date", "sr_type", "request_count", "closed_count", "open_count"],
        ["date", "sr_type"],
        f"""
        select created_date, sr_type, request_count, closed_count, open_count
        from int_311_daily
        where created_date < ? and sr_type <> '{INFO_ONLY}'
        order by created_date, sr_type
        """,
    ),
    (
        "daily_neighborhood_history.csv",
        ["date", "community_area", "request_count", "closed_count", "open_count"],
        ["date", "community_area"],
        """
        select created_date, community_area, request_count, closed_count, open_count
        from int_311_daily_by_area
        where created_date < ?
        order by created_date, community_area
        """,
    ),
]


def to_text(value):
    """Turn a database value into the text stored in the CSV."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def existing_keys(path, columns, key_columns):
    """Read the keys already in a history file (empty set if the file is new)."""
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != columns:
            raise SystemExit(f"{path.name} has unexpected columns: {reader.fieldnames}")
        return {tuple(row[k] for k in key_columns) for row in reader}


def append_new_rows(con, today, file_name, columns, key_columns, query):
    """Append rows whose key is not in the file yet. Returns how many were added."""
    path = HISTORY_DIR / file_name
    seen = existing_keys(path, columns, key_columns)
    key_index = [columns.index(k) for k in key_columns]

    new_rows = []
    for row in con.execute(query, [today]).fetchall():
        text_row = [to_text(v) for v in row]
        key = tuple(text_row[i] for i in key_index)
        if key not in seen:
            seen.add(key)
            new_rows.append(text_row)

    is_new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        if is_new_file:
            writer.writerow(columns)
        writer.writerows(new_rows)
    return len(new_rows)


def main():
    today = datetime.now(ZoneInfo("America/Chicago")).date()
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for file_name, columns, key_columns, query in HISTORY_FILES:
        added = append_new_rows(con, today, file_name, columns, key_columns, query)
        print(f"{file_name}: added {added} rows")
    con.close()


if __name__ == "__main__":
    main()
