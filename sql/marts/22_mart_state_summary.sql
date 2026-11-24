-- 22_mart_state_summary.sql
-- Grain : one row per state.
-- State league table: volume, payment per discharge (raw and case-mix
-- adjusted), median MSPB, readmission ratio and excess readmission cost,
-- ranked with window functions.

create or replace table mart_state_summary as
with s as (
    select
        state,
        any_value(region)                                                as region,
        count(*) filter (where in_inpatient)                             as hospitals_inpatient,
        sum(discharges)                                                  as discharges,
        sum(medicare_payment)                                            as medicare_payment,
        sum(medicare_payment) / sum(discharges)                          as medicare_payment_per_discharge,
        -- case-mix adjusted: divide out the DRG mix so states are compared on price
        sum(medicare_payment) / sum(discharges * case_mix_index)         as cmi_adjusted_payment_per_discharge,
        median(mspb_ratio)                                               as median_mspb_ratio,
        sum(err_weighted * hrrp_discharges_3yr) / sum(case when err_weighted is not null then hrrp_discharges_3yr end)
                                                                         as err_weighted,
        sum(excess_readmission_cost_annual_base)                         as excess_readmission_cost_annual_base
    from mart_hospital
    where state is not null
    group by state
)
select
    *,
    excess_readmission_cost_annual_base / nullif(medicare_payment, 0)    as excess_cost_pct_of_inpatient_payment,
    rank() over (order by medicare_payment_per_discharge desc nulls last)     as rank_payment_per_discharge,
    rank() over (order by cmi_adjusted_payment_per_discharge desc nulls last) as rank_cmi_adjusted_payment,
    rank() over (order by excess_readmission_cost_annual_base desc nulls last) as rank_excess_readmission_cost
from s
order by rank_payment_per_discharge;
