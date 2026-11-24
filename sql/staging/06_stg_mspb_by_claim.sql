-- 06_stg_mspb_by_claim.sql
-- Source: "Medicare Hospital Spending by Claim" (nrth-mfg3), CY2024.
-- Grain : one row per hospital (CCN) per episode period per claim type.
-- Splits each hospital's average MSPB episode spending (in $) into where the
-- money goes: index stay, readmissions, skilled nursing, home health, etc.
-- We build a short "component" label combining period and claim type.

create or replace table stg_mspb_by_claim as
with typed as (
    select
        to_ccn("Facility ID")                         as ccn,
        upper(trim("State"))                          as state,
        case
            when "Period" like '1 to 3 days Prior%'   then 'Pre-admission'
            when "Period" like 'During Index%'        then 'Index stay'
            when "Period" like '1 through 30 days%'   then 'Post-discharge'
            when "Period" like 'Complete Episode%'    then 'Complete episode'
        end                                           as episode_period,
        trim("Claim Type")                            as claim_type,
        to_num("Avg Spndg Per EP Hospital")           as spend_hospital,
        to_num("Avg Spndg Per EP State")              as spend_state,
        to_num("Avg Spndg Per EP National")           as spend_national,
        to_num("Percent of Spndg Hospital") / 100.0   as share_hospital
    from raw_mspb_by_claim
)
select
    *,
    episode_period || ': ' || claim_type as component
from typed;
