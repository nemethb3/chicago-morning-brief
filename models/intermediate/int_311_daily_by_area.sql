-- One row per date + community area (1-77), with counts by status.
-- Same status rules as int_311_daily: "closed" means Completed, Canceled, or Closed;
-- "open" means status is Open. Requests with no community area are left out, and so
-- are "311 INFORMATION ONLY CALL" rows: they are not service requests, and nearly all
-- of them are tagged to one area (Near West Side), which would swamp the ranking.

select
    created_date,
    community_area,
    count(*)                                                              as request_count,
    count(*) filter (where status in ('Completed', 'Canceled', 'Closed')) as closed_count,
    count(*) filter (where status = 'Open')                               as open_count
from {{ ref('stg_311_requests') }}
where community_area is not null
  and sr_type <> '311 INFORMATION ONLY CALL'
group by created_date, community_area
