-- One row per date of Open-Meteo daily weather, with typed columns.
-- Temperatures are in °C (with °F copies), precipitation in mm, weather_code is a WMO code.

select
    cast("date" as date)                    as weather_date,
    cast(temperature_2m_max as double)      as temp_max_c,
    cast(temperature_2m_min as double)      as temp_min_c,
    cast(temperature_2m_max as double) * 9 / 5 + 32  as temp_max_f,
    cast(temperature_2m_min as double) * 9 / 5 + 32  as temp_min_f,
    cast(precipitation_sum as double)       as precipitation_mm,
    cast(weather_code as integer)           as weather_code
from {{ source('raw', 'forecast') }}
where "date" is not null
