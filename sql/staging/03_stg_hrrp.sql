-- 03_stg_hrrp.sql
-- Source: CMS "Hospital Readmissions Reduction Program" (9n3s-kdb3), FY 2026
--         program year; performance period 07/01/2021 - 06/30/2024 (3 years).
-- Grain : one row per hospital (CCN) per HRRP condition.
--
-- Placeholders "N/A" and "Too Few to Report" become NULL. CMS suppresses the
-- discharge and readmission counts when a hospital had fewer than 11
-- readmissions, but still publishes the ratio and the predicted/expected rates
-- for many of those rows - we keep those, flagged by counts_suppressed.

create or replace table stg_hrrp as
with src as (
    select * from raw_hrrp
),
typed as (
    select
        to_ccn("Facility ID")                                  as ccn,
        trim("Facility Name")                                  as facility_name,
        upper(trim("State"))                                   as state,
        trim("Measure Name")                                   as measure_name,
        -- READM-30-HF-HRRP -> HF
        regexp_extract("Measure Name", '^READM-30-(.+)-HRRP$', 1) as condition_code,
        cast(to_num("Number of Discharges") as integer)        as discharges_3yr,
        to_num("Excess Readmission Ratio")                     as excess_readmission_ratio,
        to_num("Predicted Readmission Rate") / 100.0           as predicted_rate,
        to_num("Expected Readmission Rate") / 100.0            as expected_rate,
        cast(to_num("Number of Readmissions") as integer)      as readmissions_3yr,
        nullif(trim("Footnote"), '')                           as footnote,
        strptime("Start Date", '%m/%d/%Y')::date               as period_start,
        strptime("End Date",   '%m/%d/%Y')::date               as period_end,
        is_missing_token("Number of Discharges")
          and not is_missing_token("Excess Readmission Ratio") as counts_suppressed
    from src
)
select
    *,
    case condition_code
        when 'AMI'      then 'Acute myocardial infarction'
        when 'HF'       then 'Heart failure'
        when 'PN'       then 'Pneumonia'
        when 'COPD'     then 'COPD'
        when 'CABG'     then 'CABG surgery'
        when 'HIP-KNEE' then 'Hip/knee replacement'
    end as condition_name,
    -- number of years in the performance period (used to annualise counts)
    round(datediff('day', period_start, period_end) / 365.25, 1) as period_years
from typed
where ccn is not null;
