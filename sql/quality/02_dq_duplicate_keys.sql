-- 02_dq_duplicate_keys.sql
-- Each table must be unique on its declared grain. duplicate_keys must be 0;
-- python/transform.py fails the build if it is not.

with checks as (
    select 'stg_hospital_info'       as table_name, 'ccn'                   as grain, count(*) - count(distinct ccn) as duplicate_keys from stg_hospital_info
    union all select 'stg_hrrp',                'ccn, condition_code',       count(*) - count(distinct (ccn, condition_code)) from stg_hrrp
    union all select 'stg_inpatient',           'ccn, drg_code',             count(*) - count(distinct (ccn, drg_code)) from stg_inpatient
    union all select 'stg_mspb',                'ccn',                       count(*) - count(distinct ccn) from stg_mspb
    union all select 'stg_mspb_by_claim',       'ccn, period, claim_type',   count(*) - count(distinct (ccn, episode_period, claim_type)) from stg_mspb_by_claim
    union all select 'int_drg_national',        'drg_code',                  count(*) - count(distinct drg_code) from int_drg_national
    union all select 'int_condition_payment',   'ccn, condition_code',       count(*) - count(distinct (ccn, condition_code)) from int_condition_payment
    union all select 'mart_hospital_condition', 'ccn, condition_code',       count(*) - count(distinct (ccn, condition_code)) from mart_hospital_condition
    union all select 'mart_hospital',           'ccn',                       count(*) - count(distinct ccn) from mart_hospital
    union all select 'mart_state_summary',      'state',                     count(*) - count(distinct state) from mart_state_summary
)
select *, case when duplicate_keys = 0 then 'PASS' else 'FAIL' end as status
from checks;
