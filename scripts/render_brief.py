"""Render the daily brief as Markdown.

Reads mart_daily_brief and int_311_daily (read-only) for the current 7-day window,
and the committed history CSVs in data/history/ for the Trends and Neighborhoods
sections. Writes brief.md at the repo root. Exits with a non-zero status if the
mart is empty.
"""

import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "morning_brief.duckdb"
BRIEF_PATH = PROJECT_ROOT / "brief.md"

HISTORY_DIR = PROJECT_ROOT / "data" / "history"
AREA_NAMES_PATH = PROJECT_ROOT / "data" / "community_areas.csv"

CHICAGO = ZoneInfo("America/Chicago")
INFO_ONLY = "311 INFORMATION ONLY CALL"

# Type movers leave out Aircraft Noise Complaint (about a quarter of all requests)
# and types with fewer than this many requests in the 7-day window.
MOVERS_EXCLUDE = "Aircraft Noise Complaint"
MOVERS_MIN_REQUESTS = 20


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


def read_csv(path):
    """Read a CSV into a list of dicts (empty list if the file does not exist)."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_history():
    """Read the history CSVs into lookups keyed by date (and type or area)."""
    daily = {
        date.fromisoformat(r["date"]): int(r["total_requests"])
        for r in read_csv(HISTORY_DIR / "daily_brief_history.csv")
    }
    types = {
        (date.fromisoformat(r["date"]), r["sr_type"]): int(r["request_count"])
        for r in read_csv(HISTORY_DIR / "daily_type_history.csv")
    }
    areas = {
        (date.fromisoformat(r["date"]), int(r["community_area"])): int(r["request_count"])
        for r in read_csv(HISTORY_DIR / "daily_neighborhood_history.csv")
    }
    return daily, types, areas


def load_area_names():
    """Community area number -> name (blank names are kept blank)."""
    return {int(r["community_area"]): r["area_name"].strip() for r in read_csv(AREA_NAMES_PATH)}


def pct_change(current, base):
    """Percent change from base to current, or None if base is zero."""
    if not base:
        return None
    return 100 * (current - base) / base


def fmt_change(value):
    """Format a percent change like '+4.2%', or 'n/a' if it can't be computed."""
    return "n/a" if value is None else f"{value:+.1f}%"


def last_7_days(latest):
    """The 7 dates ending on latest, oldest first."""
    return [latest - timedelta(days=i) for i in range(6, -1, -1)]


def totals_lines(daily, today_count, now):
    """Bullet lines for the Trends totals, using complete days from history."""
    latest = max(daily)
    prev = latest - timedelta(days=1)
    week_ago = latest - timedelta(days=7)
    window = last_7_days(latest)
    lines = []

    if today_count is not None:
        lines.append(
            f"- Today so far ({fmt_date(now.date())}): {fmt_num(today_count)} requests. "
            "This is partial; the day joins history once it is complete."
        )
    lines.append(f"- Latest complete day ({fmt_date(latest)}): {fmt_num(daily[latest])} requests.")

    have = [d for d in window if d in daily]
    if len(have) == 7:
        total = sum(daily[d] for d in window)
        lines.append(
            f"- 7-day total ({fmt_date(window[0])} to {fmt_date(latest)}): {fmt_num(total)} requests."
        )
    else:
        lines.append(
            f"- 7-day total: not available yet. It needs the 7 complete days ending "
            f"{fmt_date(latest)}, and history has {len(have)} of them."
        )

    if prev in daily:
        change = fmt_change(pct_change(daily[latest], daily[prev]))
        lines.append(
            f"- Day over day: {change} ({fmt_date(latest)}, {fmt_num(daily[latest])} vs "
            f"{fmt_date(prev)}, {fmt_num(daily[prev])})."
        )
    else:
        lines.append(f"- Day over day: not available yet. It needs {fmt_date(prev)} in history.")

    if week_ago in daily:
        change = fmt_change(pct_change(daily[latest], daily[week_ago]))
        lines.append(
            f"- Week over week: {change} ({fmt_date(latest)}, {fmt_num(daily[latest])} vs "
            f"{fmt_date(week_ago)}, {fmt_num(daily[week_ago])})."
        )
    else:
        lines.append(
            f"- Week over week: not available yet. It needs {fmt_date(week_ago)} in history, "
            f"which starts {fmt_date(min(daily))}."
        )

    if len(daily) < 30:
        lines.append(f"- No 30-day trend yet: history covers {len(daily)} complete days.")
    return lines


def mover_table(movers):
    lines = [
        "| Type | 7-day count | Week over week | Day over day |",
        "|---|---:|---:|---:|",
    ]
    for m in movers:
        lines.append(
            f"| {cell(m['sr_type'])} | {fmt_num(m['window_count'])} "
            f"| {fmt_change(m['weekly'])} | {fmt_change(m['daily'])} |"
        )
    return lines


def movers_lines(daily, types):
    """Top 5 gainers and decliners by week-over-week change, from history."""
    latest = max(daily)
    prev = latest - timedelta(days=1)
    week_ago = latest - timedelta(days=7)
    window = last_7_days(latest)
    lines = ["### Type movers", ""]

    if week_ago not in daily or not all(d in daily for d in window):
        lines.append(
            f"Not available yet. Movers are ranked by week-over-week change, which needs "
            f"{fmt_date(week_ago)} and the 7 days ending {fmt_date(latest)} in history."
        )
        return lines

    def count(day, sr_type):
        # A date that is in history with no row for a type means zero requests of that type.
        return types.get((day, sr_type), 0)

    movers, skipped = [], 0
    for sr_type in sorted({t for (d, t) in types if d in window}):
        window_count = sum(count(d, sr_type) for d in window)
        if sr_type == MOVERS_EXCLUDE or window_count < MOVERS_MIN_REQUESTS:
            continue
        weekly = pct_change(count(latest, sr_type), count(week_ago, sr_type))
        if weekly is None:
            skipped += 1
            continue
        daily_change = pct_change(count(latest, sr_type), count(prev, sr_type)) if prev in daily else None
        movers.append({"sr_type": sr_type, "window_count": window_count,
                       "weekly": weekly, "daily": daily_change})

    lines.append(
        f"Week over week compares {fmt_date(latest)} with {fmt_date(week_ago)}; day over day "
        f"compares it with {fmt_date(prev)}. Only types with at least {MOVERS_MIN_REQUESTS} "
        f"requests from {fmt_date(window[0])} to {fmt_date(latest)} are included. "
        f'"{MOVERS_EXCLUDE}" and "{INFO_ONLY}" are left out.'
    )
    lines.append("")
    gainers = sorted([m for m in movers if m["weekly"] > 0], key=lambda m: (-m["weekly"], m["sr_type"]))[:5]
    decliners = sorted([m for m in movers if m["weekly"] < 0], key=lambda m: (m["weekly"], m["sr_type"]))[:5]
    lines += ["**Gainers**", ""]
    lines += mover_table(gainers) if gainers else ["No type grew week over week."]
    lines += ["", "**Decliners**", ""]
    lines += mover_table(decliners) if decliners else ["No type declined week over week."]
    if skipped:
        lines += ["", f"{skipped} type(s) had no requests on {fmt_date(week_ago)}, so no "
                      "percent change can be computed and they are left out."]
    return lines


def trends_section(daily, types, today_count, now):
    lines = ["## Trends", ""]
    if not daily:
        return lines + ["No complete days in history yet, so there are no trends to show.", ""]
    lines.append(
        f"From the committed history in `data/history/`: {len(daily)} complete days, "
        f"{fmt_date(min(daily))} to {fmt_date(max(daily))}."
    )
    lines.append("")
    lines += totals_lines(daily, today_count, now) + [""]
    lines += movers_lines(daily, types) + [""]
    return lines


def neighborhoods_section(daily, areas, names):
    """Top 5 community areas over the 7 complete days ending on the latest history date."""
    lines = ["## Neighborhoods", ""]
    if not daily:
        return lines + ["No complete days in history yet.", ""]
    window = [d for d in last_7_days(max(daily)) if d in daily]
    totals = {}
    for (day, area), n in areas.items():
        if day in window:
            totals[area] = totals.get(area, 0) + n
    grand_total = sum(totals.values())
    if not grand_total:
        return lines + ["No neighborhood history for these dates yet.", ""]

    lines.append(
        f"Top community areas from {fmt_date(window[0])} to {fmt_date(window[-1])} "
        f"({len(window)} complete days from history). Shares are of the "
        f"{fmt_num(grand_total)} service requests in that span that have a community area "
        f'(not counting "{INFO_ONLY}").'
    )
    lines.append("")
    top = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    for i, (area, n) in enumerate(top, start=1):
        name = names.get(area)
        label = f"{name} (area {area})" if name else f"Community area {area}"
        lines.append(f"{i}. {label}: {fmt_num(n)} requests, {pct(n, grand_total)}")
    return lines + [""]


def render(days, top_types, status, now):
    lines = [f"# Chicago Morning Brief: {fmt_date(now.date())}", "", summary_line(days), ""]
    lines += ["## Day by day", ""] + daily_table(days) + [""]
    lines += top_types_section(top_types) + [""]
    lines += ["## Open and closed", "", status_line(status), ""]
    weather = weather_line(days)
    if weather:
        lines += ["## Weather", "", weather, ""]
    daily, types, areas = load_history()
    today_count = days[-1]["total_requests"] if days[-1]["brief_date"] == now.date() else None
    lines += trends_section(daily, types, today_count, now)
    lines += neighborhoods_section(daily, areas, load_area_names())
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
