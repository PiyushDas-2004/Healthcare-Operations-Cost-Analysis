-- 20_mart_hospital_condition.sql
-- Grain : one row per hospital (CCN) per HRRP condition  (AMI, HF, PN, COPD,
--         CABG, HIP-KNEE).
--
-- Excess readmissions (the core estimate):
--   ERR = predicted rate / expected rate, so
--   excess readmissions = (predicted rate - expected rate) x eligible discharges
--   This is the number of readmissions above what an average hospital would
--   have had with the same patients. Negative = fewer than expected.
--   HRRP counts cover 3 years (Jul 2021 - Jun 2024); we divide by the period
--   length to get an annual figure.
--   Only POSITIVE excess is "avoidable" spend; negative values are kept for
--   the net view but not offset against other hospitals' excess.

create or replace table mart_hospital_condition as
with base as (
    select
        h.ccn,
        h.facility_name,
        h.state,
        h.condition_code,
        h.condition_name,
        h.discharges_3yr,
        h.readmissions_3yr,
        h.excess_readmission_ratio,
        h.predicted_rate,
        h.expected_rate,
        h.footnote,
        h.counts_suppressed,
        h.period_years,
        h.discharges_3yr / h.period_years                                     as discharges_annual,
        (h.predicted_rate - h.expected_rate) * h.discharges_3yr               as excess_readmissions_3yr,
        (h.predicted_rate - h.expected_rate) * h.discharges_3yr / h.period_years as excess_readmissions_annual,
        p.payment_source,
        p.cost_per_readmission_low,
        p.cost_per_readmission_base,
        p.cost_per_readmission_high
    from stg_hrrp h
    left join int_condition_payment p
           on p.ccn = h.ccn and p.condition_code = h.condition_code
),
costed as (
    select
        *,
        greatest(excess_readmissions_annual, 0)                               as positive_excess_annual,
        greatest(excess_readmissions_annual, 0) * cost_per_readmission_low    as excess_cost_annual_low,
        greatest(excess_readmissions_annual, 0) * cost_per_readmission_base   as excess_cost_annual_base,
        greatest(excess_readmissions_annual, 0) * cost_per_readmission_high   as excess_cost_annual_high,
        excess_readmissions_annual * cost_per_readmission_base                as net_excess_cost_annual_base
    from base
)
select
    *,
    -- where this hospital sits nationally for this condition (1 = worst ratio)
    case when excess_readmission_ratio is not null then
        rank() over (partition by condition_code, excess_readmission_ratio is null
                     order by excess_readmission_ratio desc) end              as err_rank_in_condition,
    case when excess_readmission_ratio is not null then
        percent_rank() over (partition by condition_code, excess_readmission_ratio is null
                             order by excess_readmission_ratio) end           as err_percentile_in_condition
from costed;
