-- 12_int_condition_payment.sql
-- Grain : one row per hospital (CCN) per HRRP condition.
-- Estimated cost of ONE readmission for each condition, three ways:
--   base : discharge-weighted average Medicare payment for the condition's DRGs
--          at that hospital; falls back to the state average, then the national
--          average, when the hospital has no published DRG cells for it.
--   high : same, but using average TOTAL payment (Medicare + beneficiary
--          cost-sharing + other primary payers) = full cost of the stay.
--   low  : national average Medicare payment for the condition's lower-severity
--          DRGs only (no MCC) - assumes avoidable readmissions are the simpler ones.

create or replace table int_condition_payment as
with cond_drg as (
    select m.condition_code, i.ccn, i.state, i.discharges, i.medicare_payment, i.total_payment
    from stg_inpatient i
    join stg_hrrp_drg_map m using (drg_code)
),
hospital_level as (
    select condition_code, ccn,
           sum(discharges)                         as cond_discharges_2024,
           sum(medicare_payment) / sum(discharges) as avg_medicare_payment,
           sum(total_payment)    / sum(discharges) as avg_total_payment
    from cond_drg group by all
),
state_level as (
    select condition_code, state,
           sum(medicare_payment) / sum(discharges) as avg_medicare_payment,
           sum(total_payment)    / sum(discharges) as avg_total_payment
    from cond_drg group by all
),
national_level as (
    select condition_code,
           sum(medicare_payment) / sum(discharges) as avg_medicare_payment,
           sum(total_payment)    / sum(discharges) as avg_total_payment
    from cond_drg group by all
),
national_low as (
    select m.condition_code,
           sum(d.medicare_payment) / sum(d.discharges) as avg_medicare_payment_no_mcc
    from int_drg_national d
    join stg_hrrp_drg_map m using (drg_code)
    where d.severity_tier <> 'MCC'
    group by all
),
hrrp_keys as (
    select distinct ccn, state, condition_code from stg_hrrp
)
select
    k.ccn,
    k.condition_code,
    h.cond_discharges_2024,
    case when h.ccn is not null then 'hospital'
         when s.state is not null then 'state'
         else 'national' end                                                     as payment_source,
    coalesce(h.avg_medicare_payment, s.avg_medicare_payment, n.avg_medicare_payment) as cost_per_readmission_base,
    coalesce(h.avg_total_payment,    s.avg_total_payment,    n.avg_total_payment)    as cost_per_readmission_high,
    l.avg_medicare_payment_no_mcc                                                    as cost_per_readmission_low,
    n.avg_medicare_payment                                                           as national_avg_medicare_payment
from hrrp_keys k
left join hospital_level h on h.ccn = k.ccn and h.condition_code = k.condition_code
left join state_level    s on s.state = k.state and s.condition_code = k.condition_code
left join national_level n on n.condition_code = k.condition_code
left join national_low   l on l.condition_code = k.condition_code;
