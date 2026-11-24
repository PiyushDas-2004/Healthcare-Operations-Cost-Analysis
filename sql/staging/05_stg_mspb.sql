-- 05_stg_mspb.sql
-- Source: "Medicare Spending Per Beneficiary - Hospital" (rrqw-56er), CY2024.
-- Grain : one row per hospital (CCN).
-- MSPB ratio = hospital's average episode spending (3 days before admission to
-- 30 days after discharge) / national median. 1.00 = national median.

create or replace table stg_mspb as
select
    to_ccn("Facility ID")             as ccn,
    upper(trim("State"))              as state,
    to_num("Score")                   as mspb_ratio,
    nullif(trim("Footnote"), '')      as mspb_footnote,
    strptime("Start Date", '%m/%d/%Y')::date as period_start,
    strptime("End Date",   '%m/%d/%Y')::date as period_end
from raw_mspb
where trim("Measure ID") = 'MSPB-1';
