# Chicago Morning Brief

[![Daily brief](https://github.com/nemethb3/chicago-morning-brief/actions/workflows/daily-brief.yml/badge.svg)](https://github.com/nemethb3/chicago-morning-brief/actions/workflows/daily-brief.yml)

A daily briefing for Chicago, built as a [dbt](https://www.getdbt.com/) project on
[DuckDB](https://duckdb.org/). Each run pulls the last 7 days of Chicago 311 service
requests and the daily weather. It then builds one table, `mart_daily_brief`, with one
row per date: temperature high and low (°F), precipitation, total 311 requests, the
most common request type that day and its count, and how many of that day's requests
are still open. `total_requests` counts every request, but `top_request_type` leaves out
"311 INFORMATION ONLY CALL", which is an information call rather than a service request.

v1 runs entirely on your machine. It uses two free data sources and needs no API keys,
accounts, or paid services. Nothing is deployed; there is no live demo.

## Data sources (v1)

1. **Chicago 311 Service Requests**: Chicago Data Portal (Socrata), dataset
   [`v6vf-nfxy`](https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy).
   Endpoint: `https://data.cityofchicago.org/resource/v6vf-nfxy.json`.
   The ingest script asks for requests created since midnight (Chicago time) six days
   ago, which covers 7 calendar days including today, with `$limit=50000`. It keeps
   `service_request_number` (named `sr_number` in the portal and renamed in the query),
   `created_date`, `closed_date`, `sr_type`, `status`, `ward`, `community_area`,
   `latitude`, and `longitude`.
2. **Open-Meteo forecast** for Chicago (lat 41.8781, lon -87.6298):
   [open-meteo.com](https://open-meteo.com/en/docs). It returns daily
   `temperature_2m_max`, `temperature_2m_min` (°C), `precipitation_sum` (mm), and
   `weather_code` (WMO code). The request adds `past_days=6`, so the weather also
   covers the same 7 days as the 311 data, plus the next 6 forecast days.

## Architecture

```
Socrata API ─┐                    ┌─ stg_311_requests ── int_311_daily ─┐
             ├─ ingest/*.py ─ raw ┤                                     ├─ mart_daily_brief
Open-Meteo ──┘   (CSV + DuckDB)   └─ stg_weather_daily ─────────────────┘
```

| Layer | Where | What it does |
|---|---|---|
| raw | `raw.requests`, `raw.forecast` (DuckDB) | Loaded by `ingest/ingest_311.py` and `ingest/ingest_weather.py`. Each run also writes a CSV to `data/raw/` and replaces its table. All columns are stored as text. |
| staging | `models/staging/` (views) | `stg_311_requests` casts dates to timestamps, trims `sr_type` and `status`, casts `ward` to integer, and drops rows without an ID or created date. `stg_weather_daily` has one typed row per date, with temperatures in °C plus °F copies. |
| intermediate | `models/intermediate/` (views) | `int_311_daily`: one row per date and request type with request, closed (Completed, Canceled, or Closed), and open counts. `int_311_daily_by_area`: the same counts per date and community area (1-77), leaving out requests with no area and information-only calls. |
| marts | `models/marts/` (table) | `mart_daily_brief`: one row per date in the 311 window, with that day's weather. Temperatures are in °F (`temp_max_f`, `temp_min_f`); staging keeps Celsius alongside them. `total_requests` includes all requests; `top_request_type` excludes information-only calls. |

Tests are in `models/schema.yml`:
- `service_request_number` must be unique and not null in staging.
- `status` must be Open, Completed, Canceled, or Closed.
- `brief_date` must be unique and not null in the mart.
- `community_area` and `request_count` must not be null in `int_311_daily_by_area`.

The DuckDB file is `morning_brief.duckdb` in the project root. `profiles.yml` also
lives in the project root, so dbt commands need `--profiles-dir .`.

## How to run

Requires Python 3.11+ and bash (on Windows, Git Bash works).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
bash run_brief.sh
```

`run_brief.sh` runs both ingest scripts, then `dbt run --profiles-dir .` and
`dbt test --profiles-dir .`, then `scripts/append_history.py`, which adds new complete
days to the history CSVs, then `scripts/render_brief.py`, which writes the brief to
[`brief.md`](brief.md). If dbt fails, the script stops before touching history or the
brief. To run dbt on its own:

```bash
dbt run --profiles-dir .
dbt test --profiles-dir .
```

To look at the result:

```bash
python -c "import duckdb; print(duckdb.connect('morning_brief.duckdb').execute('select * from mart_daily_brief').fetchall())"
```

### Daily schedule

GitHub Actions ([`.github/workflows/daily-brief.yml`](.github/workflows/daily-brief.yml))
runs `bash run_brief.sh` every morning at 12:00 UTC. It also runs on every pull request
and on every push to `main`, and it can be started by hand from the Actions tab. It
needs no secrets. Runs on `main` commit the refreshed `brief.md`, the history CSVs, and
`data/community_areas.csv` back to `main` (only when they changed); pull request runs
build the brief but commit nothing.

### Latest brief

The latest brief is in [`brief.md`](brief.md): the day-by-day table, top request types,
open and closed share, a weather note, trends, and neighborhoods, refreshed by each run
on `main`.

### History and trends

Each run replaces the raw tables, so the database only ever holds the last 7 days. The
Actions runner starts fresh every time and `morning_brief.duckdb` is gitignored, so
history can't live in the database. It lives in committed CSVs under
[`data/history/`](data/history/): one row per date (`daily_brief_history.csv`), per
date and request type (`daily_type_history.csv`, without information-only calls), and
per date and community area (`daily_neighborhood_history.csv`). `scripts/append_history.py`
only appends rows whose key is new, never rewrites a row, and adds nothing when run twice.
Only complete days are saved: today is partial, and a saved row is never updated, so a
day joins history on the run after it ends.

History began with the run that added this section, which saved its window's complete
days (Nov 11 to 16, 2026). The brief's Trends section reads only these files:

- Day-over-day change compares the latest complete day (normally yesterday) with the day
  before. It needs 2 days of history, so it works from the first run.
- Week-over-week change compares the latest complete day with the same weekday a week
  earlier. Counting today's partial day, that span is 9 dates, so weekly numbers (and the
  type movers, which rank by them) first appear on the third day's run.
- No 30-day trend is claimed until history covers 30 days.

The Neighborhoods section lists the top 5 community areas over the 7 complete days in
history, with their share of requests. Names come from
[`data/community_areas.csv`](data/community_areas.csv), built from the City of Chicago's
[Boundaries - Community Areas](https://data.cityofchicago.org/d/igwz-8jzy) dataset (names
there are upper case; "McKinley Park" and "O'Hare" follow the City's mixed-case spelling
in dataset [kn9c-c2s2](https://data.cityofchicago.org/d/kn9c-c2s2)). An area without a
verified name would show as its number only.

## Roadmap (v2 ideas, not built)

- **CTA arrivals**: add Chicago Transit Authority train and bus arrival data.
- **Snowflake swap**: run the same dbt models on Snowflake instead of DuckDB.
- **Google Calendar for your day**: a read-only pull of today's events into the brief,
  with credentials stored locally and never committed.
