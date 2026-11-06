"""Render the daily brief as Markdown from the DuckDB database.

Reads mart_daily_brief and int_311_daily (read-only) and writes brief.md at the
repo root. Exits with a non-zero status if the mart is empty.
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "morning_brief.duckdb"
BRIEF_PATH = PROJECT_ROOT / "brief.md"

CHICAGO = ZoneInfo("America/Chicago")
INFO_ONLY = "311 INFORMATION ONLY CALL"


def fetch_rows(con, sql, params=None):
    """Run a query and return a list of dicts keyed by column name."""
    cursor = con.execute(sql, params or [])
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def load_data():
    """Read everything the brief needs from the database."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    days = fetch_rows(con, "select * from mart_daily_brief order by brief_date")
    top_types = fetch_rows(
        con,
        """
        select sr_type, sum(request_count) as requests
        from int_311_daily
        where sr_type <> ?
        group by sr_type
        order by requests desc, sr_type
        limit 5
        """,
        [INFO_ONLY],
    )
    status = fetch_rows(
        con,
        """
        select sum(request_count) as total,
               sum(open_count)    as open,
               sum(closed_count)  as closed
        from int_311_daily
        """,
    )[0]
    con.close()
    return days, top_types, status


def fmt_date(d):
    """Format a date like 'Thu Nov 5, 2026'."""
    return f"{d:%a %b} {d.day}, {d.year}"


def fmt_time(dt):
    """Format a datetime like '6:05 PM Chicago time (CST)'."""
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt:%M %p} Chicago time ({dt:%Z})"


def fmt_num(value, decimals=0):
    """Format a number with thousands separators, or 'n/a' if missing."""
    if value is None:
        return "n/a"
    return f"{value:,.{decimals}f}"


def pct(part, whole):
    """Percentage of part in whole, to one decimal."""
    return f"{100 * part / whole:.1f}%"


def cell(text):
    """Make a value safe for a Markdown table cell."""
    return str(text).replace("|", "\\|")


def summary_line(days):
    total = sum(d["total_requests"] for d in days)
    busiest = max(days, key=lambda d: d["total_requests"])
    first, last = days[0]["brief_date"], days[-1]["brief_date"]
    return (
        f"Chicago logged {fmt_num(total)} requests to 311 from {fmt_date(first)} to "
        f"{fmt_date(last)}. The busiest day was {fmt_date(busiest['brief_date'])} "
        f"with {fmt_num(busiest['total_requests'])} requests."
    )


def daily_table(days):
    lines = [
        "| Date | High (°F) | Low (°F) | Precip (mm) | Requests | Top request type | Top type count | Open |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for d in days:
        lines.append(
            f"| {fmt_date(d['brief_date'])} "
            f"| {fmt_num(d['temp_max_f'], 1)} "
            f"| {fmt_num(d['temp_min_f'], 1)} "
            f"| {fmt_num(d['precipitation_mm'], 1)} "
            f"| {fmt_num(d['total_requests'])} "
            f"| {cell(d['top_request_type'] or 'n/a')} "
            f"| {fmt_num(d['top_request_type_count'])} "
            f"| {fmt_num(d['open_requests'])} |"
        )
    return lines


def top_types_section(top_types):
    lines = ["## Top request types this week", "", f'Not counting "{INFO_ONLY}".', ""]
    for i, t in enumerate(top_types, start=1):
        lines.append(f"{i}. {t['sr_type']}: {fmt_num(t['requests'])}")
    return lines


def status_line(status):
    total, open_, closed = status["total"], status["open"], status["closed"]
    return (
        f"{pct(open_, total)} of this week's requests are still open "
        f"({fmt_num(open_)}) and {pct(closed, total)} are closed ({fmt_num(closed)})."
    )


def weather_line(days):
    """Name the rainiest and warmest days, but only when the data supports it."""
    parts = []
    wet = [d for d in days if d["precipitation_mm"]]
    if wet:
        rainiest = max(wet, key=lambda d: d["precipitation_mm"])
        parts.append(
            f"The rainiest day was {fmt_date(rainiest['brief_date'])} "
            f"with {fmt_num(rainiest['precipitation_mm'], 1)} mm."
        )
    warm = [d for d in days if d["temp_max_f"] is not None]
    if warm:
        warmest = max(warm, key=lambda d: d["temp_max_f"])
        parts.append(
            f"The warmest day was {fmt_date(warmest['brief_date'])} "
            f"with a high of {fmt_num(warmest['temp_max_f'], 1)}°F."
        )
    return " ".join(parts)


def render(days, top_types, status, now):
    lines = [f"# Chicago Morning Brief: {fmt_date(now.date())}", "", summary_line(days), ""]
    lines += ["## Day by day", ""] + daily_table(days) + [""]
    lines += top_types_section(top_types) + [""]
    lines += ["## Open and closed", "", status_line(status), ""]
    weather = weather_line(days)
    if weather:
        lines += ["## Weather", "", weather, ""]
    partial_note = "The most recent day's count is partial because the day is not over yet."
    if days[-1]["brief_date"] == now.date():
        partial_note = (
            f"Today's count ({fmt_date(now.date())}) is partial because the day is not over yet."
        )
    lines += [
        "---",
        "",
        f"Generated {fmt_date(now.date())} at {fmt_time(now)}. "
        f"{partial_note} These numbers refresh daily.",
        "",
    ]
    return "\n".join(lines)


def main():
    days, top_types, status = load_data()
    if not days:
        print("mart_daily_brief has no rows; not writing brief.md", file=sys.stderr)
        sys.exit(1)
    now = datetime.now(CHICAGO)
    BRIEF_PATH.write_text(render(days, top_types, status, now), encoding="utf-8", newline="\n")
    print(f"Wrote {BRIEF_PATH.name} ({len(days)} days)")


if __name__ == "__main__":
    main()
