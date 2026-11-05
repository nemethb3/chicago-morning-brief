-- One row per 311 service request, with typed and trimmed columns.

select
    service_request_number,
    cast(created_date as timestamp)         as created_at,
    cast(closed_date as timestamp)          as closed_at,
    cast(created_date as timestamp)::date   as created_date,
    trim(sr_type)                           as sr_type,
    trim(status)                            as status,
    -- try_cast so one malformed ward does not break the run; it becomes null
    try_cast(ward as integer)               as ward,
    try_cast(community_area as integer)     as community_area,
    try_cast(latitude as double)            as latitude,
    try_cast(longitude as double)           as longitude
from {{ source('raw', 'requests') }}
where service_request_number is not null
  and created_date is not null
