-- 05_dq_value_checks.sql
-- Sanity checks on values. Each row is a rule and the number of violations.

with rules as (
    select 'CCN is 6 characters' as rule, count(*) filter (where length(ccn) <> 6) as violations from mart_hospital
    union all select 'Star rating between 1 and 5', count(*) filter (where star_rating not between 1 and 5) from mart_hospital
    union all select 'Payment per discharge > 0', count(*) filter (where medicare_payment_per_discharge <= 0) from mart_hospital
    union all select 'Medicare payment <= total payment (hospital)', count(*) filter (where medicare_payment > total_payment * 1.0001) from mart_hospital
    union all select 'ERR between 0.3 and 3', count(*) filter (where excess_readmission_ratio not between 0.3 and 3) from mart_hospital_condition
    union all select 'ERR = predicted / expected (+/- 0.001)',
              count(*) filter (where abs(excess_readmission_ratio - predicted_rate / expected_rate) > 0.001) from mart_hospital_condition
    union all select 'MSPB ratio between 0.3 and 3', count(*) filter (where mspb_ratio not between 0.3 and 3) from mart_hospital
    union all select 'MSPB components sum to episode total (+/- 2%)',
              count(*) filter (where abs(c.s - h.mspb_episode_spend) > 0.02 * h.mspb_episode_spend)
              from mart_hospital h
              join (select ccn, sum(spend_hospital) s from stg_mspb_by_claim where episode_period <> 'Complete episode' group by ccn) c using (ccn)
)
select *, case when violations = 0 then 'PASS' else 'WARN' end as status from rules;
