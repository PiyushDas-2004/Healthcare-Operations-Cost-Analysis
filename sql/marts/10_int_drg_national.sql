-- 10_int_drg_national.sql
-- Grain : one row per MS-DRG (national, all hospitals in the inpatient file).
-- Purpose:
--   1. National discharge-weighted average payment per DRG. This is the
--      "expected" price used to build each hospital's case-mix index.
--   2. Rank DRGs by total Medicare dollars and compute the running (cumulative)
--      share of spend - i.e. "which clinical services drive the bill".

create or replace table int_drg_national as
with drg_rows as (
    select
        *,
        -- MS-DRG severity tier from the description
        case
            when drg_desc ilike '%WITH MCC%' then 'MCC'
            when drg_desc ilike '%WITH CC%'  then 'CC'
            else 'None/other'
        end as severity_tier
    from stg_inpatient
),
by_drg as (
    select
        drg_code,
        any_value(drg_desc)                         as drg_desc,
        any_value(severity_tier)                    as severity_tier,
        count(distinct ccn)                         as hospitals,
        sum(discharges)                             as discharges,
        sum(medicare_payment)                       as medicare_payment,
        sum(total_payment)                          as total_payment,
        sum(medicare_payment) / sum(discharges)     as avg_medicare_payment,
        sum(total_payment)    / sum(discharges)     as avg_total_payment
    from drg_rows
    group by drg_code
),
ranked as (
    select
        *,
        rank() over (order by medicare_payment desc)                       as spend_rank,
        medicare_payment / sum(medicare_payment) over ()                   as share_of_medicare_payment,
        -- running share of national Medicare inpatient spend, largest DRG first
        sum(medicare_payment) over (order by medicare_payment desc
                                    rows between unbounded preceding and current row)
            / sum(medicare_payment) over ()                                as cumulative_share
    from by_drg
)
select * from ranked
order by spend_rank;
