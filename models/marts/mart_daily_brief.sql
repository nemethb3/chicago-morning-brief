-- One row per date in the 311 window: weather plus a summary of 311 activity.

with daily_totals as (
    select
        created_date,
        sum(request_count) as total_requests,
        sum(open_count)    as open_requests
    from {{ ref('int_311_daily') }}
    group by created_date
),

-- Rank request types within each day; ties broken alphabetically.
-- Information-only calls are not service requests, so they are left out of
-- the ranking. total_requests above still counts them.
ranked_types as (
    select
        created_date,
        sr_type,
        request_count,
        row_number() over (
            partition by created_date
            order by request_count desc, sr_type
        ) as type_rank
    from {{ ref('int_311_daily') }}
    where sr_type <> '311 INFORMATION ONLY CALL'
),

top_type as (
    select created_date, sr_type, request_count
    from ranked_types
    where type_rank = 1
)

select
    t.created_date                as brief_date,
    w.temp_max_f,
    w.temp_min_f,
    w.precipitation_mm,
    t.total_requests,
    top.sr_type                   as top_request_type,
    top.request_count             as top_request_type_count,
    t.open_requests
from daily_totals as t
left join top_type as top
    on t.created_date = top.created_date
left join {{ ref('stg_weather_daily') }} as w
    on t.created_date = w.weather_date
order by brief_date
