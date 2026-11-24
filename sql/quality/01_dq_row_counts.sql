-- 01_dq_row_counts.sql
-- Row counts for every raw, staging and mart table, so a reviewer can see
-- how many records survive each step.

select 'raw_hospital_general_info'         as table_name, 'raw'     as layer, count(*) as row_count from raw_hospital_general_info
union all select 'raw_hrrp',                          'raw',     count(*) from raw_hrrp
union all select 'raw_inpatient_by_provider_service', 'raw',     count(*) from raw_inpatient_by_provider_service
union all select 'raw_mspb',                          'raw',     count(*) from raw_mspb
union all select 'raw_mspb_by_claim',                 'raw',     count(*) from raw_mspb_by_claim
union all select 'stg_hospital_info',                 'staging', count(*) from stg_hospital_info
union all select 'stg_hrrp',                          'staging', count(*) from stg_hrrp
union all select 'stg_inpatient',                     'staging', count(*) from stg_inpatient
union all select 'stg_mspb',                          'staging', count(*) from stg_mspb
union all select 'stg_mspb_by_claim',                 'staging', count(*) from stg_mspb_by_claim
union all select 'int_drg_national',                  'mart',    count(*) from int_drg_national
union all select 'int_hospital_inpatient',            'mart',    count(*) from int_hospital_inpatient
union all select 'mart_hospital_condition',           'mart',    count(*) from mart_hospital_condition
union all select 'mart_hospital',                     'mart',    count(*) from mart_hospital
union all select 'mart_state_summary',                'mart',    count(*) from mart_state_summary;
