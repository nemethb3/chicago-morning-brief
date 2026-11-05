-- One row per date + request type, with counts by status.
-- "Closed" means Completed, Canceled, or Closed; "open" means status is Open.

select
    created_date,
    sr_type,
    count(*)                                                              as request_count,
    count(*) filter (where status in ('Completed', 'Canceled', 'Closed')) as closed_count,
    count(*) filter (where status = 'Open')                               as open_count
from {{ ref('stg_311_requests') }}
group by created_date, sr_type
