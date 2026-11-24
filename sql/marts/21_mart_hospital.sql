-- 21_mart_hospital.sql
-- Grain : one row per hospital (CCN).
-- Spine : every CCN that appears in ANY source (general info, inpatient, HRRP,
--         MSPB), so nothing is silently dropped; in_* flags show coverage.
-- Analyses filter to the rows they need (e.g. in_inpatient for payment models).

create or replace table mart_hospital as
with spine as (
    select ccn from stg_hospital_info
    union select ccn from int_hospital_inpatient
    union select distinct ccn from stg_hrrp
    union select ccn from stg_mspb
),
-- hospital-level readmission summary across the six HRRP conditions
readm as (
    select
        ccn,
        count(excess_readmission_ratio)                                          as hrrp_conditions_scored,
        sum(discharges_3yr)                                                      as hrrp_discharges_3yr,
        -- discharge-weighted mean ERR over conditions with published counts
        sum(excess_readmission_ratio * discharges_3yr) / nullif(sum(case when excess_readmission_ratio is not null then discharges_3yr end), 0)
                                                                                 as err_weighted,
        avg(excess_readmission_ratio)                                            as err_mean,
        max(excess_readmission_ratio) filter (where condition_code = 'AMI')      as err_ami,
        max(excess_readmission_ratio) filter (where condition_code = 'HF')       as err_hf,
        max(excess_readmission_ratio) filter (where condition_code = 'PN')       as err_pn,
        max(excess_readmission_ratio) filter (where condition_code = 'COPD')     as err_copd,
        max(excess_readmission_ratio) filter (where condition_code = 'CABG')     as err_cabg,
        max(excess_readmission_ratio) filter (where condition_code = 'HIP-KNEE') as err_hip_knee,
        sum(excess_readmissions_annual)                                          as net_excess_readmissions_annual,
        sum(positive_excess_annual)                                              as positive_excess_readmissions_annual,
        sum(excess_cost_annual_low)                                              as excess_readmission_cost_annual_low,
        sum(excess_cost_annual_base)                                             as excess_readmission_cost_annual_base,
        sum(excess_cost_annual_high)                                             as excess_readmission_cost_annual_high
    from mart_hospital_condition
    group by ccn
),
-- MSPB cost components, pivoted to one column per major component ($ per episode)
mspb_components as (
    select
        ccn,
        max(spend_hospital) filter (where component = 'Complete episode: Total')                 as mspb_episode_spend,
        max(spend_hospital) filter (where component = 'Index stay: Inpatient')                    as mspb_index_inpatient,
        max(spend_hospital) filter (where component = 'Index stay: Carrier')                      as mspb_index_physician,
        max(spend_hospital) filter (where component = 'Post-discharge: Inpatient')                as mspb_post_inpatient,
        max(spend_hospital) filter (where component = 'Post-discharge: Skilled Nursing Facility') as mspb_post_snf,
        max(spend_hospital) filter (where component = 'Post-discharge: Home Health Agency')       as mspb_post_home_health,
        max(spend_hospital) filter (where component = 'Post-discharge: Outpatient')               as mspb_post_outpatient,
        max(spend_hospital) filter (where component = 'Post-discharge: Carrier')                  as mspb_post_physician,
        max(spend_hospital) filter (where component = 'Post-discharge: Hospice')                  as mspb_post_hospice
    from stg_mspb_by_claim
    group by ccn
),
joined as (
    select
        s.ccn,
        coalesce(g.facility_name, ip.provider_name)              as facility_name,
        coalesce(g.state, ip.state, m.state)                     as state,
        r.region,
        r.division,
        g.hospital_type,
        g.ownership_group,
        g.ownership_detail,
        g.star_rating,
        ip.urban_rural,
        g.ccn  is not null                                       as in_general_info,
        ip.ccn is not null                                       as in_inpatient,
        rd.ccn is not null                                       as in_hrrp,
        m.mspb_ratio is not null                                 as has_mspb,
        -- volume and payments (CY2024 Medicare FFS, published DRG cells only)
        ip.discharges,
        ip.drgs_reported,
        ip.medicare_payment,
        ip.total_payment,
        ip.medicare_payment_per_discharge,
        ip.total_payment_per_discharge,
        ip.case_mix_index,
        ip.price_index,
        case
            when ip.discharges is null  then null
            when ip.discharges < 500    then '1 Small (<500)'
            when ip.discharges < 2000   then '2 Medium (500-1,999)'
            when ip.discharges < 5000   then '3 Large (2,000-4,999)'
            else                             '4 Very large (5,000+)'
        end                                                      as size_band,
        m.mspb_ratio,
        mc.* exclude (ccn),
        rd.* exclude (ccn)
    from spine s
    left join stg_hospital_info      g  on g.ccn  = s.ccn
    left join int_hospital_inpatient ip on ip.ccn = s.ccn
    left join stg_mspb               m  on m.ccn  = s.ccn
    left join mspb_components        mc on mc.ccn = s.ccn
    left join readm                  rd on rd.ccn = s.ccn
    left join stg_state_region       r  on r.state = coalesce(g.state, ip.state, m.state)
)
select
    *,
    -- ranking within state (1 = highest payment per discharge in the state)
    case when medicare_payment_per_discharge is not null then
        rank() over (partition by state, medicare_payment_per_discharge is null
                     order by medicare_payment_per_discharge desc) end           as state_rank_payment_per_discharge,
    case when discharges is not null then
        rank() over (partition by state, discharges is null
                     order by discharges desc) end                               as state_rank_volume,
    -- national percentile of payment per discharge (0 = cheapest, 1 = most expensive)
    case when medicare_payment_per_discharge is not null then
        percent_rank() over (partition by medicare_payment_per_discharge is null
                             order by medicare_payment_per_discharge) end        as national_pctile_payment_per_discharge,
    -- national volume rank and running share of discharges / Medicare dollars
    case when discharges is not null then
        row_number() over (partition by discharges is null
                           order by discharges desc, ccn) end                    as national_volume_rank,
    case when discharges is not null then
        sum(discharges) over (partition by discharges is null
                              order by discharges desc, ccn
                              rows between unbounded preceding and current row)
        / sum(discharges) over (partition by discharges is null) end             as cumulative_share_of_discharges,
    case when medicare_payment is not null then
        sum(medicare_payment) over (partition by medicare_payment is null
                                    order by medicare_payment desc, ccn
                                    rows between unbounded preceding and current row)
        / sum(medicare_payment) over (partition by medicare_payment is null) end as cumulative_share_of_medicare_payment
from joined;
