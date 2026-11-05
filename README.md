# Chicago Morning Brief

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
| intermediate | `models/intermediate/` (view) | `int_311_daily`: one row per date and request type with request, closed (Completed, Canceled, or Closed), and open counts. |
| marts | `models/marts/` (table) | `mart_daily_brief`: one row per date in the 311 window, with that day's weather. Temperatures are in °F (`temp_max_f`, `temp_min_f`); staging keeps Celsius alongside them. `total_requests` includes all requests; `top_request_type` excludes information-only calls. |

Tests are in `models/schema.yml`:
- `service_request_number` must be unique and not null in staging.
- `status` must be Open, Completed, Canceled, or Closed.
- `brief_date` must be unique and not null in the mart.

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
`dbt test --profiles-dir .`. To run dbt on its own:

```bash
dbt run --profiles-dir .
dbt test --profiles-dir .
```

To look at the result:

```bash
python -c "import duckdb; print(duckdb.connect('morning_brief.duckdb').execute('select * from mart_daily_brief').fetchall())"
```

## Findings

*Snapshot from a run on 2026-11-05 at 5:47 PM Chicago time, covering requests created
2026-10-30 through 2026-11-05. Today (2026-11-05) is partial: the day isn't over, and the
latest request in this pull was created at 1:14 PM. These numbers go stale on the next run.*

- **Volume:** 34,198 requests in the window. The busiest day was 2026-11-03 with 6,282.
  The quietest was 2026-11-05 with 2,336, but that day is partial; the quietest full day
  was 2026-10-31 with 4,046.
- **Top request types** (excluding "311 INFORMATION ONLY CALL", which had 9,492 calls):
  Aircraft Noise Complaint 10,306; Graffiti Removal Request 1,897; Rodent Baiting/Rat
  Complaint 909; Abandoned Vehicle Complaint 881; Garbage Cart Maintenance 863.
- **Open vs. closed:** 7,212 requests (21.1%) are open and 26,986 (78.9%) are closed
  (Completed, Canceled, or Closed).
- **Weather:** the rainiest day was 2026-11-01 with 1.1 mm. The busiest 311 day
  (2026-11-03) was dry and the warmest day (high 70.9°F). There is no clear pattern
  between weather and request volume in this window: 2026-10-30, the second-busiest day
  (6,085), was dry with a high of 54.9°F, and seven days is too few to say more.
- **Wards:** excluding information-only calls, Ward 41 had 10,507 requests. The next
  highest, Ward 32, had 513. Of Ward 41's requests, 10,255 were Aircraft Noise Complaints.

## Roadmap (v2 ideas, not built)

- **CTA arrivals**: add Chicago Transit Authority train and bus arrival data.
- **Snowflake swap**: run the same dbt models on Snowflake instead of DuckDB.
- **Daily schedule**: run the pipeline automatically every morning.
- **Google Calendar for your day**: a read-only pull of today's events into the brief,
  with credentials stored locally and never committed.
